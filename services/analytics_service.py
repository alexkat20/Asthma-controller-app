"""Анализ за период, график динамики и прогноз (текст + графики в base64 для чата)."""

from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from repositories import database as db
from services import forecast_service
from utils.dates import adapt_where_for_alias, build_date_filter
from utils.formatting import FLAG_RU, ZONE_RU
from utils.plotting import fig_to_data_uri


def run_analysis(user_id: str, days, custom_range) -> tuple:
    where, extra_params, label = build_date_filter(days, custom_range)
    conn = db.get_connection()
    df = db.fetch_readings_df(conn, user_id, where, extra_params)
    if df.empty:
        conn.close()
        return f"Нет данных за {label}.", []

    df["date"] = pd.to_datetime(df["date"])
    df["day_key"] = df["date"].dt.normalize()
    daily = df.groupby("day_key", as_index=False)["maximum"].mean()

    flags = db.fetch_flags_df(conn, user_id, where, extra_params)
    meds = db.fetch_medicine_doses_df(
        conn, user_id, adapt_where_for_alias(where, "tm"), extra_params
    )
    conn.close()

    merged = daily.copy()
    flag_cols = ["sport", "sickness", "stress", "allergy", "flight"]
    if not flags.empty:
        flags["day_key"] = pd.to_datetime(flags["date"]).dt.normalize()
        flags_agg = flags.groupby("day_key", as_index=False)[flag_cols].max()
        merged = merged.merge(flags_agg, on="day_key", how="left")
    for col in flag_cols:
        if col not in merged.columns:
            merged[col] = 0
    merged[flag_cols] = merged[flag_cols].fillna(0)

    med_cols = []
    if not meds.empty:
        meds["day_key"] = pd.to_datetime(meds["date"]).dt.normalize()
        pivot = meds.pivot_table(
            index="day_key",
            columns="medicine_name",
            values="doses",
            aggfunc="sum",
            fill_value=0,
        )
        pivot = pivot.reset_index()
        merged = merged.merge(pivot, on="day_key", how="left")
        med_cols = [c for c in pivot.columns if c != "day_key"]
        merged[med_cols] = merged[med_cols].fillna(0)

    merged["weekday"] = merged["day_key"].dt.day_name()
    weekday_dummies = pd.get_dummies(merged["weekday"], prefix="день")

    corr_input = pd.concat(
        [merged[["maximum"] + flag_cols + med_cols], weekday_dummies], axis=1
    )
    corr_matrix = (
        corr_input.corr(numeric_only=True)[["maximum"]].drop(index="maximum").dropna()
    )

    avg, mn, mx = df["maximum"].mean(), df["maximum"].min(), df["maximum"].max()
    trend = (
        "рост"
        if df["maximum"].iloc[-1] > df["maximum"].iloc[0]
        else "снижение"
        if df["maximum"].iloc[-1] < df["maximum"].iloc[0]
        else "стабильно"
    )

    images = []
    top_factors = ""
    if not corr_matrix.empty:
        plt.figure(figsize=(5, max(2.5, 0.32 * len(corr_matrix))))
        sns.heatmap(
            corr_matrix, annot=True, cmap="coolwarm", center=0, fmt=".2f", cbar=False
        )
        plt.title("Корреляция с максимумом пикфлоу")
        plt.tight_layout()
        images.append(fig_to_data_uri())
        top = corr_matrix["maximum"].abs().sort_values(ascending=False).head(3)
        top_factors = "\nСильнее всего связаны с максимумом: " + ", ".join(top.index)

    text = (
        f"📊 Анализ за {label}\n"
        f"Среднее: {avg:.0f}, минимум: {mn:.0f}, максимум: {mx:.0f}\n"
        f"Тренд за период: {trend}"
        f"{top_factors}"
    )
    return text, images


def run_plot(user_id: str, days, custom_range) -> tuple:
    where, extra_params, label = build_date_filter(days, custom_range)
    conn = db.get_connection()
    df = db.fetch_readings_df(conn, user_id, where, extra_params)
    thresholds = db.calculate_zone_thresholds(conn, user_id, datetime.now())
    conn.close()

    if df.empty:
        return f"Нет данных за {label}.", []

    df["date"] = pd.to_datetime(df["date"])

    plt.figure(figsize=(8, 4))
    if thresholds:
        top = max(df["maximum"].max(), thresholds.green_zone) * 1.05
        plt.axhspan(thresholds.green_zone, top, color="#2F9E44", alpha=0.08)
        plt.axhspan(
            thresholds.yellow_zone, thresholds.green_zone, color="#E8A33D", alpha=0.12
        )
        plt.axhspan(0, thresholds.yellow_zone, color="#D14343", alpha=0.08)
    plt.plot(df["date"], df["maximum"], marker="o", color="#3E6FB0", label="показания")
    if len(df) >= 5:
        df["trend"] = df["maximum"].rolling(5, min_periods=1).mean()
        plt.plot(
            df["date"],
            df["trend"],
            linestyle="--",
            color="#444",
            label="тренд (скольз. среднее)",
        )
    plt.title(f"Динамика пикфлоу — {label}")
    plt.xlabel("Дата")
    plt.ylabel("Пикфлоу")
    plt.grid(alpha=0.3)
    plt.xticks(rotation=40)
    plt.legend()
    image = fig_to_data_uri()

    return f"📈 График за {label}.", [image]


def run_predict(user_id: str) -> tuple:
    conn = db.get_connection()
    today = forecast_service.forecast_today(conn, user_id)
    week = forecast_service.forecast_week(conn, user_id)
    conn.close()

    if today is None:
        return (
            "Недостаточно данных для прогноза — сначала запишите несколько показаний.",
            [],
        )

    lines = [
        f"🔮 Прогноз на сегодня ({today['date'].strftime('%d.%m')}): ~{today['predicted_value']:.0f}, "
        f"зона: {ZONE_RU[today['zone']]}"
    ]
    if today["active_flags_used"]:
        lines.append(
            "Учтено вчерашнее состояние: "
            + ", ".join(FLAG_RU[f] for f in today["active_flags_used"])
        )
    slope = today["trend_slope_per_day"]
    if abs(slope) >= 0.5:
        direction = "рост" if slope > 0 else "снижение"
        lines.append(
            f"Тренд последних недель: {direction} ~{abs(slope):.1f} л/мин в день."
        )

    plt.figure(figsize=(7, 3.3))
    dates = [d["date"] for d in week]
    values = [d["predicted_value"] for d in week]
    colors = {
        "green": "#2F9E44",
        "yellow": "#E8A33D",
        "red": "#D14343",
        "unknown": "#999",
    }
    plt.plot(dates, values, color="#3E6FB0", zorder=1)
    plt.scatter(dates, values, c=[colors[d["zone"]] for d in week], zorder=2, s=60)
    plt.title("Прогноз на ближайшую неделю")
    plt.ylabel("Пикфлоу")
    plt.grid(alpha=0.3)
    plt.xticks(rotation=30)
    image = fig_to_data_uri()

    lines.append(
        "\n📅 На неделю вперёд (без учёта будущих факторов, кроме сегодняшнего):"
    )
    for d in week:
        lines.append(
            f"  {d['date'].strftime('%d.%m')}: ~{d['predicted_value']:.0f} ({ZONE_RU[d['zone']]})"
        )

    return "\n".join(lines), [image]
