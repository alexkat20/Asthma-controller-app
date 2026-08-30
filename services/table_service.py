from datetime import datetime, timedelta

import pandas as pd

from repositories.extra_info_repository import EXTRA_INFO_FLAGS
from repositories.unit_of_work import UnitOfWork
from utils.dates import PERIOD_RU, classify_period
from utils.formatting import FLAG_RU

MIN_DAYS = 1
MAX_DAYS = 31
DEFAULT_DAYS = 7


def _classify(maximum, green_zone, yellow_zone) -> str:
    if pd.isna(green_zone) or pd.isna(yellow_zone):
        return "unknown"
    if maximum >= green_zone:
        return "green"
    if maximum >= yellow_zone:
        return "yellow"
    return "red"


def _period_label(days: int) -> str:
    return f"{days} дн." if days != 1 else "1 день"


def _profile_caption(profile: dict | None) -> str:
    if not profile or not (profile.get("height_cm") or profile.get("weight_kg")):
        return ""
    parts = []
    if profile.get("height_cm"):
        parts.append(f"рост {profile['height_cm']:.0f} см")
    if profile.get("weight_kg"):
        parts.append(f"вес {profile['weight_kg']:.0f} кг")
    return "\n" + ", ".join(parts).capitalize() + "."


def _collect(user_id: str, days: int):
    days = max(MIN_DAYS, min(MAX_DAYS, days))
    end = datetime.now()
    start = end - timedelta(days=days)
    start_str = start.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end.strftime("%Y-%m-%d %H:%M:%S")

    with UnitOfWork() as uow:
        readings = uow.readings.fetch_full_readings_df(user_id, start_str, end_str)
        meds = uow.medicines.fetch_medicine_doses_df(user_id, start_str, end_str)
        extra = uow.extra_info.fetch_extra_info_full_df(user_id, start_str, end_str)
        profile = uow.profiles.get_profile(user_id)

    label = _period_label(days)

    if readings.empty:
        return None

    readings = readings.sort_values("date")

    meds_by_date = {}
    if not meds.empty:
        for date_val, group in meds.groupby("date"):
            meds_by_date[date_val] = list(group.itertuples())

    extra_by_date = (
        {row.date: row for row in extra.itertuples()} if not extra.empty else {}
    )

    return readings, meds_by_date, extra_by_date, profile, label


def build_table_data(user_id: str, days: int):
    collected = _collect(user_id, days)
    if collected is None:
        return f"Нет данных за последние {_period_label(days)}.", None
    readings, meds_by_date, extra_by_date, profile, label = collected

    rows = []
    medicine_options = set()
    for r in readings.itertuples():
        dt = pd.to_datetime(r.date)
        period = classify_period(dt)
        zone = _classify(r.maximum, r.green_zone, r.yellow_zone)

        med_entries = meds_by_date.get(r.date, [])
        medicine_names = [m.medicine_name for m in med_entries]
        medicine_options.update(medicine_names)
        medicines_display = (
            ", ".join(f"{m.medicine_name}×{m.doses}" for m in med_entries) or "—"
        )

        extra_row = extra_by_date.get(r.date)
        if extra_row is not None:
            active_flags = [
                FLAG_RU[f] for f in EXTRA_INFO_FLAGS if getattr(extra_row, f)
            ]
            state_display = ", ".join(active_flags) or "нет"
            attacks = (
                None
                if pd.isna(extra_row.attacks_count)
                else int(extra_row.attacks_count)
            )
        else:
            state_display = "—"
            attacks = None

        rows.append(
            {
                "date_time": dt.strftime("%d.%m %H:%M"),
                "date_raw": r.date,
                "period": period,
                "period_label": PERIOD_RU[period].capitalize(),
                "attempts": f"{r.first_try:.0f}/{r.second_try:.0f}/{r.third_try:.0f}",
                "max": r.maximum,
                "zone": zone,
                "medicines": medicine_names,
                "medicines_display": medicines_display,
                "attacks": attacks,
                "state_display": state_display,
            }
        )

    table = {
        "columns": [
            {"key": "date_time", "label": "Дата/время", "sortKey": "date_raw"},
            {"key": "period_label", "label": "Период"},
            {"key": "attempts", "label": "Попытки"},
            {"key": "max", "label": "Макс."},
            {"key": "medicines_display", "label": "Препараты"},
            {"key": "attacks", "label": "Приступы"},
            {"key": "state_display", "label": "Состояние"},
        ],
        "rows": rows,
        "medicine_options": sorted(medicine_options),
        "period_options": [
            PERIOD_RU["morning"].capitalize(),
            PERIOD_RU["evening"].capitalize(),
        ],
    }

    caption = f"🗓 Таблица за последние {label} ({len(rows)} записей)."
    caption += _profile_caption(profile)
    return caption, table
