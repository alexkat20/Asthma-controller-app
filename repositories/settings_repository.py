from sqlalchemy import select

from repositories.db_engine import get_session
from repositories.orm_models import Reminder, UserLocation


def save_user_location(user_id: str, label: str, lat: float, lon: float) -> None:
    conn = get_session()
    try:
        existing = conn.get(UserLocation, user_id)
        if existing:
            existing.city_label = label
            existing.lat = lat
            existing.lon = lon
        else:
            conn.add(UserLocation(user_id=user_id, city_label=label, lat=lat, lon=lon))
        conn.commit()
    finally:
        conn.close()


def get_user_location(user_id: str):
    conn = get_session()
    try:
        row = conn.get(UserLocation, user_id)
        if row is None:
            return None
        return {"label": row.city_label, "lat": row.lat, "lon": row.lon}
    finally:
        conn.close()


def upsert_reminder(user_id: str, hour: int, minute: int) -> None:
    conn = get_session()
    try:
        existing = conn.get(Reminder, user_id)
        if existing:
            existing.hour = hour
            existing.minute = minute
        else:
            conn.add(
                Reminder(user_id=user_id, hour=hour, minute=minute, last_sent=None)
            )
        conn.commit()
    finally:
        conn.close()


def get_reminder(user_id: str):
    conn = get_session()
    try:
        row = conn.get(Reminder, user_id)
        return (row.hour, row.minute) if row else None
    finally:
        conn.close()


def get_all_reminders() -> list:
    conn = get_session()
    try:
        rows = conn.execute(
            select(Reminder.user_id, Reminder.hour, Reminder.minute, Reminder.last_sent)
        ).all()
        return [(r.user_id, r.hour, r.minute, r.last_sent) for r in rows]
    finally:
        conn.close()


def mark_reminder_sent(user_id: str, date_str: str) -> None:
    conn = get_session()
    try:
        reminder = conn.get(Reminder, user_id)
        if reminder:
            reminder.last_sent = date_str
            conn.commit()
    finally:
        conn.close()
