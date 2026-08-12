"""Репозиторий анкеты пользователя (user_profile)."""

from datetime import datetime

from sqlalchemy import select

from repositories.db_engine import get_session
from repositories.orm_models import UserProfile


def profile_exists(user_id: str) -> bool:
    conn = get_session()
    try:
        return conn.get(UserProfile, user_id) is not None
    finally:
        conn.close()


def get_profile(user_id: str):
    conn = get_session()
    try:
        row = conn.get(UserProfile, user_id)
        if row is None:
            return None
        return {
            "gender": row.gender,
            "age": row.age,
            "height_cm": row.height_cm,
            "weight_kg": row.weight_kg,
            "smoking": row.smoking,
            "allergies": [a for a in (row.allergies or "").split(",") if a],
        }
    finally:
        conn.close()


def get_created_at(user_id: str):
    conn = get_session()
    try:
        row = conn.get(UserProfile, user_id)
        return row.created_at if row else None
    finally:
        conn.close()


def list_user_ids() -> list:
    conn = get_session()
    try:
        return list(conn.execute(select(UserProfile.user_id)).scalars().all())
    finally:
        conn.close()


def save_profile(user_id: str, data: dict) -> None:
    conn = get_session()
    try:
        existing = conn.get(UserProfile, user_id)
        allergies_str = ",".join(data.get("allergies") or [])
        if existing:
            existing.gender = data.get("gender")
            existing.age = data.get("age")
            existing.height_cm = data.get("height_cm")
            existing.weight_kg = data.get("weight_kg")
            existing.smoking = data.get("smoking")
            existing.allergies = allergies_str
            # created_at умышленно не трогаем — это точка отсчёта для ACT, не должна сдвигаться
        else:
            conn.add(
                UserProfile(
                    user_id=user_id,
                    gender=data.get("gender"),
                    age=data.get("age"),
                    height_cm=data.get("height_cm"),
                    weight_kg=data.get("weight_kg"),
                    smoking=data.get("smoking"),
                    allergies=allergies_str,
                    created_at=datetime.now().isoformat(),
                )
            )
        conn.commit()
    finally:
        conn.close()
