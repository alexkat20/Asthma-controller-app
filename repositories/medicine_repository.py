import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from repositories.db_engine import get_session
from repositories.orm_models import Medicine, TakenMedicine
from repositories import user_repository


def _find_user_medicine(conn: Session, user_id: str, medicine_name: str):
    """Ищет препарат пользователя без учёта регистра"""
    target = medicine_name.strip().lower()
    rows = conn.execute(select(Medicine).where(Medicine.user_id == user_id)).scalars()
    for med in rows:
        if med.medicine_name.strip().lower() == target:
            return med
    return None


def _get_or_create_medicine_id(
    conn: Session, user_id: str, medicine_name: str, dose: str = ""
) -> int:
    existing = _find_user_medicine(conn, user_id, medicine_name)
    if existing:
        return existing.medicine_id

    medicine = Medicine(user_id=user_id, medicine_name=medicine_name, dose=dose)
    conn.add(medicine)
    conn.flush()  # получить medicine_id, не завершая внешнюю транзакцию
    return medicine.medicine_id


def _add_taken_medicine(
    conn: Session, medicine_id: int, user_id: str, doses: int, date_str: str
) -> None:
    conn.add(
        TakenMedicine(
            medicine_id=medicine_id, user_id=user_id, doses=doses, date=date_str
        )
    )


def add_medicine(user_id: str, medicine_name: str, dose: str = "") -> str:
    """Добавляет препарат в личный список пользователя"""
    conn = get_session()
    try:
        user_repository._ensure_user(conn, user_id)
        existing = _find_user_medicine(conn, user_id, medicine_name)
        if existing:
            if dose and dose != (existing.dose or ""):
                existing.dose = dose
                conn.commit()
                return "dose_updated"
            return "exists"

        conn.add(Medicine(user_id=user_id, medicine_name=medicine_name, dose=dose))
        conn.commit()
        return "created"
    finally:
        conn.close()


def list_medicine_names(user_id: str) -> list:
    conn = get_session()
    try:
        return list(
            conn.execute(
                select(Medicine.medicine_name).where(Medicine.user_id == user_id)
            )
            .scalars()
            .all()
        )
    finally:
        conn.close()


def list_medicines_with_doses(user_id: str) -> list:
    """Возвращает [(medicine_name, dose), ...] только для этого пользователя."""
    conn = get_session()
    try:
        rows = conn.execute(
            select(Medicine.medicine_name, Medicine.dose)
            .where(Medicine.user_id == user_id)
            .order_by(Medicine.medicine_name)
        ).all()
        return [(r.medicine_name, r.dose) for r in rows]
    finally:
        conn.close()


def fetch_medicine_doses_df(user_id: str, start_str: str, end_str: str) -> pd.DataFrame:
    conn = get_session()
    try:
        stmt = (
            select(TakenMedicine.date, Medicine.medicine_name, TakenMedicine.doses)
            .join(Medicine, Medicine.medicine_id == TakenMedicine.medicine_id)
            .where(
                TakenMedicine.user_id == user_id,
                TakenMedicine.date >= start_str,
                TakenMedicine.date <= end_str,
            )
        )
        return pd.DataFrame(
            conn.execute(stmt).all(), columns=["date", "medicine_name", "doses"]
        )
    finally:
        conn.close()


def fetch_all_taken_medicine_with_names_df(user_id: str) -> pd.DataFrame:
    conn = get_session()
    try:
        stmt = (
            select(TakenMedicine.date, Medicine.medicine_name)
            .join(Medicine, Medicine.medicine_id == TakenMedicine.medicine_id)
            .where(TakenMedicine.user_id == user_id)
        )
        return pd.DataFrame(conn.execute(stmt).all(), columns=["date", "medicine_name"])
    finally:
        conn.close()
