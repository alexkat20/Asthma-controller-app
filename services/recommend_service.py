import pandas as pd

from models.domain import ZoneThresholds
from repositories import database as dbmod

RU_MEDICINE_NOTE = (
    "на основе истории — не является медицинской рекомендацией, "
    "при ухудшении состояния проконсультируйтесь с врачом"
)


def _classify_row(row) -> str:
    if pd.isna(row["green_zone"]) or pd.isna(row["yellow_zone"]):
        return "unknown"
    thresholds = ZoneThresholds(
        personal_best=0, green_zone=row["green_zone"], yellow_zone=row["yellow_zone"]
    )
    return dbmod.classify_zone(row["maximum"], thresholds)


def recommend_medicine(conn, user_id: str, min_occurrences: int = 3) -> dict | None:
    readings = dbmod.fetch_all_readings_with_zones_df(conn, user_id)
    if readings.empty:
        return None

    readings["date"] = pd.to_datetime(readings["date"])
    readings["day"] = readings["date"].dt.normalize()
    daily = readings.sort_values("maximum").groupby("day", as_index=False).first()
    daily["zone"] = daily.apply(_classify_row, axis=1)

    bad_days = daily[daily["zone"].isin(["yellow", "red"])].copy()
    if bad_days.empty:
        return None

    zone_by_day = daily.set_index("day")["zone"]
    bad_days["next_day"] = bad_days["day"] + pd.Timedelta(days=1)
    bad_days["recovered_next_day"] = bad_days["next_day"].map(
        lambda d: (zone_by_day.get(d) == "green") if d in zone_by_day.index else None
    )
    bad_days = bad_days.dropna(subset=["recovered_next_day"])
    if bad_days.empty:
        return None

    meds = dbmod.fetch_all_taken_medicine_with_names_df(conn, user_id)
    if meds.empty:
        return None
    meds["day"] = pd.to_datetime(meds["date"]).dt.normalize()

    baseline_recovery = float(bad_days["recovered_next_day"].mean())

    stats: dict = {}
    for _, row in bad_days.iterrows():
        day_meds = (
            meds.loc[meds["day"] == row["day"], "medicine_name"].unique().tolist()
        )
        for med in day_meds:
            s = stats.setdefault(med, {"used": 0, "recovered": 0})
            s["used"] += 1
            s["recovered"] += int(row["recovered_next_day"])

    candidates = [
        {
            "medicine": med,
            "used": s["used"],
            "recovery_rate": s["recovered"] / s["used"],
        }
        for med, s in stats.items()
        if s["used"] >= min_occurrences
    ]

    if not candidates:
        med_counts = meds.loc[
            meds["day"].isin(bad_days["day"]), "medicine_name"
        ].value_counts()
        if med_counts.empty:
            return None
        top_medicine = med_counts.idxmax()
        return {
            "medicine": top_medicine,
            "confidence": "low",
            "recovery_rate": None,
            "used": int(med_counts.max()),
            "baseline_recovery_rate": baseline_recovery,
            "note": f"недостаточно повторов для статистики восстановления — показан просто самый часто используемый"
                    f" в такие дни препарат ({RU_MEDICINE_NOTE})",
        }

    candidates.sort(key=lambda c: (c["recovery_rate"], c["used"]), reverse=True)
    best = candidates[0]
    confidence = "high" if best["used"] >= 6 else "medium"

    return {
        "medicine": best["medicine"],
        "confidence": confidence,
        "recovery_rate": best["recovery_rate"],
        "used": best["used"],
        "baseline_recovery_rate": baseline_recovery,
        "note": RU_MEDICINE_NOTE,
    }


def format_recommendation(rec: dict) -> str:
    if rec is None:
        return ""
    conf_ru = {
        "high": "высокая уверенность",
        "medium": "средняя уверенность",
        "low": "низкая уверенность",
    }[rec["confidence"]]
    if rec["recovery_rate"] is not None:
        pct = round(rec["recovery_rate"] * 100)
        base = (
            f" (в среднем по всем ухудшениям — {round(rec['baseline_recovery_rate']*100)}%)"
            if rec.get("baseline_recovery_rate") is not None
            else ""
        )
        return (
            f"💊 На основе истории стоит рассмотреть: {rec['medicine']}\n"
            f"После него в {pct}% случаев ({rec['used']} набл.) состояние на следующий день "
            f"возвращалось в зелёную зону{base}. {conf_ru.capitalize()}.\n"
            f"({rec['note']})"
        )
    return (
        f"💊 Возможный вариант на основе истории: {rec['medicine']} "
        f"(использовался в {rec['used']} похожих случаях). {rec['note']}"
    )
