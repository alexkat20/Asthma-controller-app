"""Репозиторий анкеты пользователя (user_profile)."""

import sqlite3
from datetime import datetime

from repositories.database import get_connection


def ensure_profile_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profile (
            user_id TEXT PRIMARY KEY,
            gender TEXT,
            age INTEGER,
            height_cm REAL,
            weight_kg REAL,
            smoking TEXT,
            allergies TEXT,
            created_at TEXT
        )
        """
    )


def profile_exists(user_id: str) -> bool:
    conn = get_connection()
    ensure_profile_table(conn)
    row = conn.execute(
        "SELECT 1 FROM user_profile WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return row is not None


def get_profile(user_id: str):
    conn = get_connection()
    ensure_profile_table(conn)
    row = conn.execute(
        "SELECT gender, age, height_cm, weight_kg, smoking, allergies FROM user_profile WHERE user_id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "gender": row[0],
        "age": row[1],
        "height_cm": row[2],
        "weight_kg": row[3],
        "smoking": row[4],
        "allergies": [a for a in (row[5] or "").split(",") if a],
    }


def get_created_at(user_id: str):
    conn = get_connection()
    ensure_profile_table(conn)
    row = conn.execute(
        "SELECT created_at FROM user_profile WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def list_user_ids() -> list:
    conn = get_connection()
    ensure_profile_table(conn)
    ids = [
        row[0] for row in conn.execute("SELECT user_id FROM user_profile").fetchall()
    ]
    conn.close()
    return ids


def save_profile(user_id: str, data: dict) -> None:
    conn = get_connection()
    ensure_profile_table(conn)
    conn.execute(
        """
        INSERT INTO user_profile (user_id, gender, age, height_cm, weight_kg, smoking, allergies, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            gender=excluded.gender, age=excluded.age, height_cm=excluded.height_cm,
            weight_kg=excluded.weight_kg, smoking=excluded.smoking, allergies=excluded.allergies
        """,
        (
            user_id,
            data.get("gender"),
            data.get("age"),
            data.get("height_cm"),
            data.get("weight_kg"),
            data.get("smoking"),
            ",".join(data.get("allergies") or []),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
