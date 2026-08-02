"""Репозиторий вспомогательных настроек: местоположение пользователя и напоминания."""

import sqlite3


def ensure_location_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_location (
            user_id TEXT PRIMARY KEY, city_label TEXT, lat REAL, lon REAL
        )
        """
    )


def save_user_location(
    conn: sqlite3.Connection, user_id: str, label: str, lat: float, lon: float
) -> None:
    ensure_location_table(conn)
    conn.execute(
        """
        INSERT INTO user_location (user_id, city_label, lat, lon) VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET city_label=excluded.city_label, lat=excluded.lat, lon=excluded.lon
        """,
        (user_id, label, lat, lon),
    )
    conn.commit()


def get_user_location(conn: sqlite3.Connection, user_id: str):
    ensure_location_table(conn)
    row = conn.execute(
        "SELECT city_label, lat, lon FROM user_location WHERE user_id=?", (user_id,)
    ).fetchone()
    if row is None:
        return None
    return {"label": row[0], "lat": row[1], "lon": row[2]}


def ensure_reminders_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            user_id TEXT PRIMARY KEY, hour INTEGER, minute INTEGER, last_sent TEXT
        )
        """
    )


def upsert_reminder(
    conn: sqlite3.Connection, user_id: str, hour: int, minute: int
) -> None:
    ensure_reminders_table(conn)
    conn.execute(
        """
        INSERT INTO reminders (user_id, hour, minute, last_sent) VALUES (?, ?, ?, NULL)
        ON CONFLICT(user_id) DO UPDATE SET hour = excluded.hour, minute = excluded.minute
        """,
        (user_id, hour, minute),
    )
    conn.commit()


def get_reminder(conn: sqlite3.Connection, user_id: str):
    ensure_reminders_table(conn)
    return conn.execute(
        "SELECT hour, minute FROM reminders WHERE user_id=?", (user_id,)
    ).fetchone()


def get_all_reminders(conn: sqlite3.Connection) -> list:
    ensure_reminders_table(conn)
    return conn.execute(
        "SELECT user_id, hour, minute, last_sent FROM reminders"
    ).fetchall()


def mark_reminder_sent(conn: sqlite3.Connection, user_id: str, date_str: str) -> None:
    conn.execute(
        "UPDATE reminders SET last_sent=? WHERE user_id=?", (date_str, user_id)
    )
