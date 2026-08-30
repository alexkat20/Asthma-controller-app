import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from repositories.db_engine import get_session
from repositories.orm_models import ExtraInfo

EXTRA_INFO_FLAGS = ["sport", "sickness", "stress", "allergy", "flight"]


def _add_extra_info(
    conn: Session,
    user_id: str,
    date_str: str,
    flags: dict,
    attacks_count: int | None = None,
    record_time: str | None = None,
) -> None:
    conn.add(
        ExtraInfo(
            user_id=user_id,
            date=date_str,
            sport=flags.get("sport", False),
            sickness=flags.get("sickness", False),
            stress=flags.get("stress", False),
            allergy=flags.get("allergy", False),
            flight=flags.get("flight", False),
            attacks_count=attacks_count,
            record_time=record_time,
        )
    )


def fetch_flags_df(user_id: str, start_str: str, end_str: str) -> pd.DataFrame:
    conn = get_session()
    try:
        stmt = select(
            ExtraInfo.date,
            ExtraInfo.sport,
            ExtraInfo.sickness,
            ExtraInfo.stress,
            ExtraInfo.allergy,
            ExtraInfo.flight,
        ).where(
            ExtraInfo.user_id == user_id,
            ExtraInfo.date >= start_str,
            ExtraInfo.date <= end_str,
        )
        return pd.DataFrame(
            conn.execute(stmt).all(),
            columns=["date", "sport", "sickness", "stress", "allergy", "flight"],
        )
    finally:
        conn.close()


def fetch_flags_since_df(user_id: str, since_str: str) -> pd.DataFrame:
    conn = get_session()
    try:
        stmt = select(
            ExtraInfo.date,
            ExtraInfo.sport,
            ExtraInfo.sickness,
            ExtraInfo.stress,
            ExtraInfo.allergy,
            ExtraInfo.flight,
        ).where(ExtraInfo.user_id == user_id, ExtraInfo.date >= since_str)
        return pd.DataFrame(
            conn.execute(stmt).all(),
            columns=["date", "sport", "sickness", "stress", "allergy", "flight"],
        )
    finally:
        conn.close()


def fetch_extra_info_full_df(
    user_id: str, start_str: str, end_str: str
) -> pd.DataFrame:
    conn = get_session()
    try:
        stmt = select(
            ExtraInfo.date,
            ExtraInfo.sport,
            ExtraInfo.sickness,
            ExtraInfo.stress,
            ExtraInfo.allergy,
            ExtraInfo.flight,
            ExtraInfo.attacks_count,
            ExtraInfo.record_time,
        ).where(
            ExtraInfo.user_id == user_id,
            ExtraInfo.date >= start_str,
            ExtraInfo.date <= end_str,
        )
        return pd.DataFrame(
            conn.execute(stmt).all(),
            columns=[
                "date",
                "sport",
                "sickness",
                "stress",
                "allergy",
                "flight",
                "attacks_count",
                "record_time",
            ],
        )
    finally:
        conn.close()
