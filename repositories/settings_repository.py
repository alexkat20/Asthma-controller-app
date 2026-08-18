from sqlalchemy import select
from sqlalchemy.orm import Session

from repositories.orm_models import Reminder, UserLocation


def save_user_location(
    conn: Session, user_id: str, label: str, lat: float, lon: float
) -> None:
    existing = conn.get(UserLocation, user_id)
    if existing:
        existing.city_label = label
        existing.lat = lat
        existing.lon = lon
    else:
        conn.add(UserLocation(user_id=user_id, city_label=label, lat=lat, lon=lon))
    conn.commit()


def get_user_location(conn: Session, user_id: str):
    row = conn.get(UserLocation, user_id)
    if row is None:
        return None
    return {"label": row.city_label, "lat": row.lat, "lon": row.lon}


def upsert_reminder(conn: Session, user_id: str, hour: int, minute: int) -> None:
    existing = conn.get(Reminder, user_id)
    if existing:
        existing.hour = hour
        existing.minute = minute
    else:
        conn.add(Reminder(user_id=user_id, hour=hour, minute=minute, last_sent=None))
    conn.commit()


def get_reminder(conn: Session, user_id: str):
    row = conn.get(Reminder, user_id)
    return (row.hour, row.minute) if row else None


def get_all_reminders(conn: Session) -> list:
    rows = conn.execute(
        select(Reminder.user_id, Reminder.hour, Reminder.minute, Reminder.last_sent)
    ).all()
    return [(r.user_id, r.hour, r.minute, r.last_sent) for r in rows]


def mark_reminder_sent(conn: Session, user_id: str, date_str: str) -> None:
    reminder = conn.get(Reminder, user_id)
    if reminder:
        reminder.last_sent = date_str
