"""
Прогноз пикфлоу на сегодня и на ближайшую неделю.

Метод — прозрачный и объяснимый (не "чёрный ящик"), собран из трёх компонент:

1. baseline: среднее по последним 14 показаниям.
2. trend: наклон линейной регрессии по последним 21 дню (куда движется
   пикфлоу в последнее время — вверх/вниз).
3. weekday_effect: систематическое отклонение конкретного дня недели от
   общего среднего (например, если по понедельникам после выходных с
   тренировками пикфлоу обычно чуть ниже).
4. flags_effect: средний исторический эффект состояний (спорт/стресс/
   аллергия/болезнь/перелёт) ПРЕДЫДУЩЕГО дня на пикфлоу СЛЕДУЮЩЕГО —
   используется только для прогноза на сегодня (вчерашние флаги уже
   известны); для остальных дней недели вперёд состояния неизвестны,
   поэтому эта компонента не применяется — это явное упрощение, о котором
   бот сообщает пользователю.

Такой подход сознательно проще ML-модели, но каждое число в прогнозе можно
объяснить пользователю одной фразой — это важнее точности до долей единицы
на выборке из нескольких сотен точек.
"""

from datetime import datetime

import numpy as np
import pandas as pd

import db as dbmod

FLAG_COLUMNS = ["sport", "sickness", "stress", "allergy", "flight"]


def _load_history(conn, user_id: str, lookback_days: int = 365) -> pd.DataFrame:
    df = pd.read_sql(
        """
        SELECT date, maximum FROM readings
        WHERE user_id = ? AND maximum IS NOT NULL
          AND date >= datetime('now', ?)
        ORDER BY date
        """,
        conn,
        params=(user_id, f"-{lookback_days} days"),
    )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def _load_flags(conn, user_id: str, lookback_days: int = 365) -> pd.DataFrame:
    df = pd.read_sql(
        f"""
        SELECT date, {", ".join(FLAG_COLUMNS)} FROM extra_info
        WHERE user_id = ? AND date >= datetime('now', ?)
        ORDER BY date
        """,
        conn,
        params=(user_id, f"-{lookback_days} days"),
    )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df


def _weekday_effect(df: pd.DataFrame) -> dict:
    if len(df) < 14:
        return {}
    overall_mean = df["maximum"].mean()
    effects = {}
    for wd, group in df.groupby(df["date"].dt.weekday):
        if len(group) >= 3:
            effects[wd] = float(group["maximum"].mean() - overall_mean)
    return effects


def _trend_slope(df: pd.DataFrame, window_days: int = 21) -> float:
    if df.empty:
        return 0.0
    recent = df[df["date"] >= df["date"].max() - pd.Timedelta(days=window_days)]
    if len(recent) < 4:
        return 0.0
    x = (recent["date"] - recent["date"].min()).dt.days.values.astype(float)
    y = recent["maximum"].values.astype(float)
    slope, _ = np.polyfit(x, y, 1)
    return float(slope)


def _flag_effects(readings_df: pd.DataFrame, flags_df: pd.DataFrame) -> dict:
    """Средний эффект (л/мин) каждого флага за ПРЕДЫДУЩИЙ день на maximum текущего дня."""
    if flags_df.empty or readings_df.empty:
        return {}
    merged = readings_df.copy()
    merged["prev_date"] = merged["date"] - pd.Timedelta(days=1)
    baseline_mean = readings_df["maximum"].mean()

    effects = {}
    for flag in FLAG_COLUMNS:
        flagged_dates = set(flags_df.loc[flags_df[flag] == 1, "date"])
        if len(flagged_dates) < 3:
            continue
        mask = merged["prev_date"].isin(flagged_dates)
        if mask.sum() < 3:
            continue
        effects[flag] = float(merged.loc[mask, "maximum"].mean() - baseline_mean)
    return effects


def _active_flags_for_date(flags_df: pd.DataFrame, date: pd.Timestamp) -> list:
    if flags_df.empty:
        return []
    rows = flags_df[flags_df["date"] == date]
    if rows.empty:
        return []
    row = rows.iloc[-1]
    return [f for f in FLAG_COLUMNS if bool(row.get(f))]


def _predict_value(
    baseline, last_date, target_date, weekday_effects, slope, flag_effects, active_flags
):
    days_ahead = max((target_date - last_date).days, 0)
    trend_component = slope * days_ahead
    weekday_component = weekday_effects.get(target_date.weekday(), 0.0)
    flags_component = sum(flag_effects.get(f, 0.0) for f in active_flags)
    return baseline + trend_component + weekday_component + flags_component


def _build_context(conn, user_id):
    df = _load_history(conn, user_id)
    if df.empty:
        return None
    flags_df = _load_flags(conn, user_id)
    return {
        "df": df,
        "flags_df": flags_df,
        "baseline": df.tail(14)["maximum"].mean(),
        "last_date": df["date"].max(),
        "weekday_effects": _weekday_effect(df),
        "slope": _trend_slope(df),
        "flag_effects": _flag_effects(df, flags_df),
    }


def forecast_today(conn, user_id: str) -> dict | None:
    ctx = _build_context(conn, user_id)
    if ctx is None:
        return None

    today = pd.Timestamp(datetime.now().date())
    yesterday = today - pd.Timedelta(days=1)
    active_flags = _active_flags_for_date(ctx["flags_df"], yesterday)

    predicted = _predict_value(
        ctx["baseline"],
        ctx["last_date"],
        today,
        ctx["weekday_effects"],
        ctx["slope"],
        ctx["flag_effects"],
        active_flags,
    )

    thresholds = dbmod.calculate_zone_thresholds(conn, user_id, datetime.now())
    zone = dbmod.classify_zone(predicted, thresholds) if thresholds else "unknown"

    return {
        "date": today.date(),
        "predicted_value": round(float(predicted), 1),
        "zone": zone,
        "thresholds": thresholds,
        "active_flags_used": active_flags,
        "trend_slope_per_day": round(ctx["slope"], 2),
        "days_since_last_reading": max((today - ctx["last_date"]).days, 0),
    }


def forecast_week(conn, user_id: str) -> list:
    ctx = _build_context(conn, user_id)
    if ctx is None:
        return []

    thresholds = dbmod.calculate_zone_thresholds(conn, user_id, datetime.now())
    today = pd.Timestamp(datetime.now().date())
    yesterday = today - pd.Timedelta(days=1)

    results = []
    for i in range(7):
        target = today + pd.Timedelta(days=i)
        # Флаги известны только для "сегодня" (по вчерашнему дню); дальше в будущее
        # состояние пользователя неизвестно, поэтому компонента флагов не применяется.
        active_flags = (
            _active_flags_for_date(ctx["flags_df"], yesterday) if i == 0 else []
        )
        predicted = _predict_value(
            ctx["baseline"],
            ctx["last_date"],
            target,
            ctx["weekday_effects"],
            ctx["slope"],
            ctx["flag_effects"],
            active_flags,
        )
        zone = dbmod.classify_zone(predicted, thresholds) if thresholds else "unknown"
        results.append(
            {
                "date": target.date(),
                "predicted_value": round(float(predicted), 1),
                "zone": zone,
            }
        )
    return results
