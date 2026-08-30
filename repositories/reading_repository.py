from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import bindparam, func, select, update
from sqlalchemy.orm import Session

from models.domain import (
    GREEN_RATIO,
    YELLOW_RATIO,
    ZoneThresholds,
    classify_zone,
    thresholds_from_personal_best,
)
from repositories import extra_info_repository, medicine_repository, user_repository
from repositories.db_engine import get_session
from repositories.orm_models import Reading

# Персональный рекорд считается по данным за этот период (в днях)
DEFAULT_ZONE_WINDOW_DAYS = 90

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_IMPORT_TIME = "23:00:00"

_EXTRA_INFO_ALIASES = {
    "sick": "sickness",
    "sickness": "sickness",
    "sport": "sport",
    "спорт": "sport",
    "stress": "stress",
    "стресс": "stress",
    "allergy": "allergy",
    "аллергия": "allergy",
    "болезнь": "sickness",
    "болел": "sickness",
    "flight": "flight",
    "перелёт": "flight",
    "перелет": "flight",
}


def _to_date_str(value) -> str:
    if isinstance(value, str):
        return value
    return value.strftime(DATE_FORMAT)


def _calculate_zone_thresholds(
    conn: Session,
    user_id: str,
    as_of_date,
    window_days: int = DEFAULT_ZONE_WINDOW_DAYS,
) -> ZoneThresholds | None:
    if isinstance(as_of_date, str):
        as_of_date = datetime.fromisoformat(as_of_date.split(" ")[0].replace("/", "-"))

    as_of_str = as_of_date.strftime(DATE_FORMAT)
    window_start_str = (as_of_date - timedelta(days=window_days)).strftime(DATE_FORMAT)

    personal_best = conn.execute(
        select(func.max(Reading.maximum)).where(
            Reading.user_id == user_id,
            Reading.maximum.isnot(None),
            Reading.date <= as_of_str,
            Reading.date >= window_start_str,
        )
    ).scalar_one_or_none()

    if personal_best is None:
        return None
    return thresholds_from_personal_best(personal_best)


def calculate_zone_thresholds(
    user_id: str,
    as_of_date,
    window_days: int = DEFAULT_ZONE_WINDOW_DAYS,
) -> ZoneThresholds | None:
    conn = get_session()
    try:
        return _calculate_zone_thresholds(conn, user_id, as_of_date, window_days)
    finally:
        conn.close()


def _recalculate_zones_for_user_history(
    conn: Session, user_id: str, window_days: int = DEFAULT_ZONE_WINDOW_DAYS
) -> int:
    """Пересчитывает green_zone/yellow_zone для ВСЕЙ истории пользователя"""
    rows = conn.execute(
        select(Reading.id, Reading.date, Reading.maximum)
        .where(Reading.user_id == user_id)
        .order_by(Reading.date)
    ).all()
    if not rows:
        return 0

    df = pd.DataFrame(rows, columns=["id", "date", "maximum"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    personal_best = df["maximum"].rolling(f"{window_days}D", min_periods=1).max()

    updates = []
    reset = df.reset_index()
    for idx, pb in zip(reset.index, personal_best.values):
        row_id = int(reset.iloc[idx]["id"])
        updates.append(
            {
                "b_id": row_id,
                "green_zone": round(pb * GREEN_RATIO, 1),
                "yellow_zone": round(pb * YELLOW_RATIO, 1),
                "red_zone": 0.0,
            }
        )

    if updates:
        conn.connection().execute(
            update(Reading)
            .where(Reading.id == bindparam("b_id"))
            .values(
                green_zone=bindparam("green_zone"),
                yellow_zone=bindparam("yellow_zone"),
                red_zone=bindparam("red_zone"),
            ),
            updates,
        )
    conn.commit()
    return len(updates)


def _insert_reading(
    conn: Session,
    user_id: str,
    date,
    first_try: float,
    second_try: float,
    third_try: float,
) -> tuple:
    """Вставляет новую запись и сразу считает для неё зоны"""
    maximum = max(first_try, second_try, third_try)
    date_str = _to_date_str(date)

    thresholds = _calculate_zone_thresholds(
        conn, user_id, date, DEFAULT_ZONE_WINDOW_DAYS
    )
    if thresholds is None:
        thresholds = thresholds_from_personal_best(maximum)
    else:
        thresholds = thresholds_from_personal_best(
            max(thresholds.personal_best, maximum)
        )

    reading = Reading(
        user_id=user_id,
        date=date_str,
        first_try=first_try,
        second_try=second_try,
        third_try=third_try,
        maximum=maximum,
        green_zone=thresholds.green_zone,
        yellow_zone=thresholds.yellow_zone,
        red_zone=thresholds.red_zone,
    )
    conn.add(reading)
    conn.flush()

    zone = classify_zone(maximum, thresholds)
    return reading.id, thresholds, zone


def save_reading_entry(
    user_id: str,
    when: datetime,
    first_try: float,
    second_try: float,
    third_try: float,
    medicine_name: str | None = None,
    doses: int | None = None,
    flags: dict | None = None,
    attacks_count: int | None = None,
    record_time: str | None = None,
) -> tuple:
    date_str = when.strftime(DATE_FORMAT)
    conn = get_session()
    try:
        user_repository._ensure_user(conn, user_id)
        _, thresholds, zone = _insert_reading(
            conn, user_id, when, first_try, second_try, third_try
        )

        if medicine_name and doses:
            medicine_id = medicine_repository._get_or_create_medicine_id(
                conn, user_id, medicine_name
            )
            medicine_repository._add_taken_medicine(
                conn, medicine_id, user_id, doses, date_str
            )

        flags = flags or {}
        if attacks_count is not None or any(flags.values()):
            extra_info_repository._add_extra_info(
                conn, user_id, date_str, flags, attacks_count, record_time
            )

        conn.commit()
        return thresholds, zone
    finally:
        conn.close()


def _parse_extra_info_cell(cell: str) -> dict:
    flags = {f: False for f in extra_info_repository.EXTRA_INFO_FLAGS}
    if not cell or (isinstance(cell, float) and pd.isna(cell)):
        return flags
    tokens = [t.strip().lower() for t in str(cell).split(",") if t.strip()]
    for token in tokens:
        mapped = _EXTRA_INFO_ALIASES.get(token)
        if mapped:
            flags[mapped] = True
    return flags


def import_dataframe(df: pd.DataFrame, user_id: str) -> dict:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    required = {"First try", "Second try", "Third try", "Date"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"В файле не хватает колонок: {', '.join(sorted(missing))}")

    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    bad_dates = df["Date"].isna().sum()
    df = df.dropna(subset=["Date"])

    known_non_medicine_cols = {
        "First try",
        "Second try",
        "Third try",
        "Maximum",
        "Date",
        "Green Zone",
        "Yellow Zone",
        "Red Zone",
        "Extra info",
    }
    medicine_cols = [c for c in df.columns if c not in known_non_medicine_cols]

    readings_inserted = 0
    doses_inserted = 0
    extra_info_inserted = 0

    conn = get_session()
    try:
        user_repository._ensure_user(conn, user_id)
        for med_name in medicine_cols:
            medicine_repository._get_or_create_medicine_id(conn, user_id, med_name)

        for _, row in df.iterrows():
            date_str = row["Date"].strftime(f"%Y-%m-%d {DEFAULT_IMPORT_TIME}")

            first_try = row.get("First try")
            second_try = row.get("Second try")
            third_try = row.get("Third try")
            if pd.isna(first_try) or pd.isna(second_try) or pd.isna(third_try):
                continue

            maximum = (
                float(row["Maximum"])
                if "Maximum" in df.columns and not pd.isna(row.get("Maximum"))
                else max(first_try, second_try, third_try)
            )
            conn.add(
                Reading(
                    user_id=user_id,
                    date=date_str,
                    first_try=float(first_try),
                    second_try=float(second_try),
                    third_try=float(third_try),
                    maximum=maximum,
                    green_zone=None,
                    yellow_zone=None,
                    red_zone=None,
                )
            )
            readings_inserted += 1

            for med_name in medicine_cols:
                doses = row.get(med_name)
                if pd.isna(doses) or doses == 0:
                    continue
                medicine_id = medicine_repository._get_or_create_medicine_id(
                    conn, user_id, med_name
                )
                medicine_repository._add_taken_medicine(
                    conn, medicine_id, user_id, int(doses), date_str
                )
                doses_inserted += 1

            if "Extra info" in df.columns:
                flags = _parse_extra_info_cell(row.get("Extra info"))
                if any(flags.values()):
                    extra_info_repository._add_extra_info(
                        conn, user_id, date_str, flags
                    )
                    extra_info_inserted += 1

        conn.commit()
        updated_zone_rows = _recalculate_zones_for_user_history(conn, user_id)
    finally:
        conn.close()

    return {
        "rows_in_file": len(df),
        "readings_inserted": readings_inserted,
        "doses_inserted": doses_inserted,
        "extra_info_inserted": extra_info_inserted,
        "zone_rows_recalculated": updated_zone_rows,
        "bad_dates_skipped": int(bad_dates),
    }


def fetch_full_readings_df(user_id: str, start_str: str, end_str: str) -> pd.DataFrame:
    conn = get_session()
    try:
        stmt = (
            select(
                Reading.date,
                Reading.first_try,
                Reading.second_try,
                Reading.third_try,
                Reading.maximum,
                Reading.green_zone,
                Reading.yellow_zone,
                Reading.red_zone,
            )
            .where(
                Reading.user_id == user_id,
                Reading.date >= start_str,
                Reading.date <= end_str,
            )
            .order_by(Reading.date)
        )
        return pd.DataFrame(
            conn.execute(stmt).all(),
            columns=[
                "date",
                "first_try",
                "second_try",
                "third_try",
                "maximum",
                "green_zone",
                "yellow_zone",
                "red_zone",
            ],
        )
    finally:
        conn.close()


def fetch_readings_df(user_id: str, start_str: str, end_str: str) -> pd.DataFrame:
    conn = get_session()
    try:
        stmt = (
            select(Reading.date, Reading.maximum)
            .where(
                Reading.user_id == user_id,
                Reading.maximum.isnot(None),
                Reading.date >= start_str,
                Reading.date <= end_str,
            )
            .order_by(Reading.date)
        )
        return pd.DataFrame(conn.execute(stmt).all(), columns=["date", "maximum"])
    finally:
        conn.close()


def fetch_history_since_df(user_id: str, since_str: str) -> pd.DataFrame:
    """Вся история с определённой даты, без верхней границы — для прогноза."""
    conn = get_session()
    try:
        stmt = (
            select(Reading.date, Reading.maximum)
            .where(
                Reading.user_id == user_id,
                Reading.maximum.isnot(None),
                Reading.date >= since_str,
            )
            .order_by(Reading.date)
        )
        return pd.DataFrame(conn.execute(stmt).all(), columns=["date", "maximum"])
    finally:
        conn.close()


def fetch_all_readings_with_zones_df(user_id: str) -> pd.DataFrame:
    """Вся история показаний с уже посчитанными на тот момент зонами —
    для recommend_service.py."""
    conn = get_session()
    try:
        stmt = (
            select(
                Reading.date, Reading.maximum, Reading.green_zone, Reading.yellow_zone
            )
            .where(
                Reading.user_id == user_id,
                Reading.maximum.isnot(None),
                Reading.green_zone.isnot(None),
            )
            .order_by(Reading.date)
        )
        return pd.DataFrame(
            conn.execute(stmt).all(),
            columns=["date", "maximum", "green_zone", "yellow_zone"],
        )
    finally:
        conn.close()
