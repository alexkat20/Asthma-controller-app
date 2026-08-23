from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from repositories import database as dbmod
from utils.dates import classify_period

FLAG_COLUMNS = ["sport", "sickness", "stress", "allergy", "flight"]


def _load_history(
    conn, user_id: str, period: str | None = None, lookback_days: int = 365
) -> pd.DataFrame:
    """period=None — вся история (как раньше, смешивая утро/вечер).
    period="morning"/"evening" — только записи этого времени суток, чтобы
    прогноз на утро строился по утренней истории, а на вечер — по вечерней
    (утренние показания в среднем всегда ниже вечерних — это нормальная
    суточная динамика лёгких, а не ухудшение; смешивать их в одну базовую
    линию означало бы искажать оба прогноза)."""
    since_str = (datetime.now() - timedelta(days=lookback_days)).strftime(
        dbmod.DATE_FORMAT
    )
    df = dbmod.fetch_history_since_df(conn, user_id, since_str)
    if df.empty:
        return df
    if period is not None:
        df = df[df["date"].map(classify_period) == period].reset_index(drop=True)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def _load_flags(conn, user_id: str, lookback_days: int = 365) -> pd.DataFrame:
    since_str = (datetime.now() - timedelta(days=lookback_days)).strftime(
        dbmod.DATE_FORMAT
    )
    df = dbmod.fetch_flags_since_df(conn, user_id, since_str)
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
    if np.unique(x).size < 2:
        return 0.0
    try:
        slope, _ = np.polyfit(x, y, 1)
    except np.linalg.LinAlgError:
        return 0.0
    return float(slope)


def _flag_effects(readings_df: pd.DataFrame, flags_df: pd.DataFrame) -> dict:
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


def _build_context(conn, user_id, period: str | None = None):
    df = _load_history(conn, user_id, period=period)
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


def forecast_today(conn, user_id: str, period: str | None = None) -> dict | None:
    ctx = _build_context(conn, user_id, period=period)
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


def forecast_week(conn, user_id: str, period: str | None = None) -> list:
    ctx = _build_context(conn, user_id, period=period)
    if ctx is None:
        return []

    thresholds = dbmod.calculate_zone_thresholds(conn, user_id, datetime.now())
    today = pd.Timestamp(datetime.now().date())
    yesterday = today - pd.Timedelta(days=1)

    results = []
    for i in range(7):
        target = today + pd.Timedelta(days=i)
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


def forecast_today_by_period(conn, user_id: str) -> dict:
    """{"morning": прогноз_или_None, "evening": прогноз_или_None} — раздельно,
    каждый строится по истории только своего времени суток."""
    return {
        "morning": forecast_today(conn, user_id, period="morning"),
        "evening": forecast_today(conn, user_id, period="evening"),
    }


def forecast_week_by_period(conn, user_id: str) -> dict:
    return {
        "morning": forecast_week(conn, user_id, period="morning"),
        "evening": forecast_week(conn, user_id, period="evening"),
    }
