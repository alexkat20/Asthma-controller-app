from datetime import datetime

import matplotlib

matplotlib.use("Agg")

import pandas as pd
import seaborn as sns
from matplotlib.figure import Figure

from repositories import extra_info_repository, medicine_repository, reading_repository
from services import forecast_service
from utils.dates import ALL_TIME, build_date_filter, classify_period
from utils.formatting import FLAG_RU, ZONE_RU
from utils.plotting import fig_to_data_uri

_PERIOD_COLOR = {"morning": "#F2A93B", "evening": "#3E6FB0"}
_PERIOD_TREND_COLOR = {"morning": "#B26A00", "evening": "#1C3F73"}
_PERIOD_LABEL = {"morning": "утро", "evening": "вечер"}
_ZONE_COLOR = {
    "green": "#2F9E44",
    "yellow": "#E8A33D",
    "red": "#D14343",
    "unknown": "#999",
}


def _diurnal_variation_text(df: pd.DataFrame) -> str:
    """Сравнивает утренние и вечерние показания по дням, где есть ОБА замера —
    отдельно от общей статистики, чтобы явно показать, ухудшается ли состояние
    к вечеру (это реальный клинический показатель: суточная изменчивость
    пикфлоу >10% — признанный маркер недостаточного контроля астмы, а не
    просто нормальный разброс)."""
    morning = df[df["period"] == "morning"]
    evening = df[df["period"] == "evening"]
    if morning.empty or evening.empty:
        return ""

    m_by_day = morning.groupby(morning["date"].dt.normalize())["maximum"].mean()
    e_by_day = evening.groupby(evening["date"].dt.normalize())["maximum"].mean()
    common_days = m_by_day.index.intersection(e_by_day.index)
    if len(common_days) < 3:
        return ""

    diffs = e_by_day.loc[common_days] - m_by_day.loc[common_days]
    avg_diff = diffs.mean()
    mean_morning = m_by_day.loc[common_days].mean()
    pct_diff = (avg_diff / mean_morning * 100) if mean_morning else 0.0

    if pct_diff <= -10:
        interp = (
            f"к вечеру в среднем хуже на {abs(pct_diff):.0f}% ({abs(avg_diff):.0f} л/мин) — "
            "заметная суточная изменчивость, стоит обсудить с врачом"
        )
    elif pct_diff >= 10:
        interp = f"к вечеру в среднем лучше на {pct_diff:.0f}% ({avg_diff:.0f} л/мин)"
    else:
        interp = f"стабильно в течение дня (разница {pct_diff:+.0f}%)"

    return (
        f"\n🌗 Суточная динамика (по {len(common_days)} дн. с двумя замерами): {interp}."
    )


def run_analysis(user_id: str, days, custom_range) -> tuple:
    start_str, end_str, label = build_date_filter(days, custom_range)
    df = reading_repository.fetch_readings_df(user_id, start_str, end_str)
    if df.empty:
        return f"Нет данных за {label}.", []

    df["date"] = pd.to_datetime(df["date"])
    df["period"] = df["date"].map(classify_period)
    df["day_key"] = df["date"].dt.normalize()
    daily = df.groupby("day_key", as_index=False)["maximum"].mean()

    flags = extra_info_repository.fetch_flags_df(user_id, start_str, end_str)
    meds = medicine_repository.fetch_medicine_doses_df(user_id, start_str, end_str)

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

    period_lines = []
    for period in ("morning", "evening"):
        sub = df[df["period"] == period]
        if sub.empty:
            continue
        period_lines.append(
            f"{_PERIOD_LABEL[period].capitalize()}: среднее {sub['maximum'].mean():.0f}, "
            f"мин {sub['maximum'].min():.0f}, макс {sub['maximum'].max():.0f} ({len(sub)} зам.)"
        )
    period_block = ("\n" + "\n".join(period_lines)) if period_lines else ""
    diurnal_block = _diurnal_variation_text(df)

    images = []
    top_factors = ""
    if not corr_matrix.empty:
        fig = Figure(figsize=(5, max(2.5, 0.32 * len(corr_matrix))))
        ax = fig.add_subplot(111)
        sns.heatmap(
            corr_matrix,
            annot=True,
            cmap="coolwarm",
            center=0,
            fmt=".2f",
            cbar=False,
            ax=ax,
        )
        ax.set_title("Корреляция с максимумом пикфлоу")
        fig.tight_layout()
        images.append(fig_to_data_uri(fig))
        top = corr_matrix["maximum"].abs().sort_values(ascending=False).head(3)
        top_factors = "\nСильнее всего связаны с максимумом: " + ", ".join(top.index)

    text = (
        f"📊 Анализ за {label}\n"
        f"Среднее: {avg:.0f}, минимум: {mn:.0f}, максимум: {mx:.0f}\n"
        f"Тренд за период: {trend}"
        f"{period_block}"
        f"{diurnal_block}"
        f"{top_factors}"
    )
    return text, images


def run_plot(user_id: str, days, custom_range) -> tuple:
    start_str, end_str, label = build_date_filter(days, custom_range)
    df = reading_repository.fetch_readings_df(user_id, start_str, end_str)
    thresholds = reading_repository.calculate_zone_thresholds(user_id, datetime.now())

    if df.empty:
        return f"Нет данных за {label}.", []

    df["date_full"] = pd.to_datetime(df["date"])
    df["period"] = df["date_full"].map(classify_period)
    df["date"] = df["date_full"].dt.date

    fig = Figure(figsize=(8, 4))
    ax = fig.add_subplot(111)
    if thresholds:
        top = max(df["maximum"].max(), thresholds.green_zone) * 1.05
        ax.axhspan(thresholds.green_zone, top, color="#2F9E44", alpha=0.08)
        ax.axhspan(
            thresholds.yellow_zone, thresholds.green_zone, color="#E8A33D", alpha=0.12
        )
        ax.axhspan(0, thresholds.yellow_zone, color="#D14343", alpha=0.08)

    # Утро и вечер — отдельными линиями (не смешиваем): утренний пикфлоу в норме
    # почти всегда ниже вечернего сам по себе (обычная суточная физиология лёгких,
    # а не ухудшение), поэтому единая смешанная линия маскирует и тренд, и
    # реальную суточную разницу между "как было утром" и "как было вечером".
    for period in ("morning", "evening"):
        sub = df[df["period"] == period].sort_values("date")
        if sub.empty:
            continue
        ax.plot(
            sub["date"],
            sub["maximum"],
            marker="o",
            color=_PERIOD_COLOR[period],
            label=_PERIOD_LABEL[period],
        )
        if len(sub) >= 5:
            trend = sub["maximum"].rolling(5, min_periods=1).mean()
            ax.plot(
                sub["date"],
                trend,
                linestyle="--",
                color=_PERIOD_TREND_COLOR[period],
                linewidth=2.0,
                zorder=5,
                label=f"{_PERIOD_LABEL[period]} — тренд",
            )

    ax.set_title(f"Динамика пикфлоу — {label}")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Пикфлоу")
    ax.grid(alpha=0.3)
    ax.tick_params(axis="x", labelrotation=40)
    ax.legend()
    if not (custom_range is None and days == ALL_TIME):
        ax.set_xlim(pd.to_datetime(start_str), pd.to_datetime(end_str))

    fig.tight_layout()
    image = fig_to_data_uri(fig)

    return f"📈 График за {label} — утро и вечер отдельными линиями.", [image]


def run_predict(user_id: str) -> tuple:
    today = forecast_service.forecast_today_by_period(user_id)
    week = forecast_service.forecast_week_by_period(user_id)

    today_m, today_e = today["morning"], today["evening"]
    week_m, week_e = week["morning"], week["evening"]

    if today_m is None and today_e is None:
        return (
            "Недостаточно данных для прогноза — сначала запишите несколько показаний.",
            [],
        )

    lines = ["🔮 Прогноз на сегодня:"]
    for period, data in (("morning", today_m), ("evening", today_e)):
        if data:
            lines.append(
                f"  {_PERIOD_LABEL[period].capitalize()}: ~{data['predicted_value']:.0f}, "
                f"зона: {ZONE_RU[data['zone']]}"
            )
        else:
            lines.append(
                f"  {_PERIOD_LABEL[period].capitalize()}: пока недостаточно "
                f"{'утренней' if period == 'morning' else 'вечерней'} истории"
            )

    reference = today_e or today_m
    if reference["active_flags_used"]:
        lines.append(
            "Учтено вчерашнее состояние: "
            + ", ".join(FLAG_RU[f] for f in reference["active_flags_used"])
        )

    for period, data in (("morning", today_m), ("evening", today_e)):
        if data and abs(data["trend_slope_per_day"]) >= 0.5:
            slope = data["trend_slope_per_day"]
            direction = "рост" if slope > 0 else "снижение"
            lines.append(
                f"Тренд ({_PERIOD_LABEL[period]}): {direction} ~{abs(slope):.1f} л/мин в день."
            )

    fig = Figure(figsize=(7, 3.5))
    ax = fig.add_subplot(111)
    for period, week_data in (("morning", week_m), ("evening", week_e)):
        if not week_data:
            continue
        dates = [d["date"] for d in week_data]
        values = [d["predicted_value"] for d in week_data]
        ax.plot(
            dates,
            values,
            color=_PERIOD_COLOR[period],
            label=_PERIOD_LABEL[period],
            zorder=1,
        )
        ax.scatter(
            dates,
            values,
            c=[_ZONE_COLOR[d["zone"]] for d in week_data],
            edgecolors=_PERIOD_COLOR[period],
            linewidths=1.5,
            zorder=2,
            s=60,
        )
    ax.set_title("Прогноз на ближайшую неделю")
    ax.set_ylabel("Пикфлоу")
    ax.grid(alpha=0.3)
    ax.tick_params(axis="x", labelrotation=30)
    ax.legend()
    fig.tight_layout()
    image = fig_to_data_uri(fig)

    lines.append(
        "\n📅 На неделю вперёд (без учёта будущих факторов, кроме сегодняшнего):"
    )
    week_days = week_m or week_e
    for i in range(len(week_days)):
        date_str = week_days[i]["date"].strftime("%d.%m")
        parts = []
        if week_m:
            parts.append(
                f"утро ~{week_m[i]['predicted_value']:.0f} ({ZONE_RU[week_m[i]['zone']]})"
            )
        if week_e:
            parts.append(
                f"вечер ~{week_e[i]['predicted_value']:.0f} ({ZONE_RU[week_e[i]['zone']]})"
            )
        lines.append(f"  {date_str}: " + ", ".join(parts))

    return "\n".join(lines), [image]
