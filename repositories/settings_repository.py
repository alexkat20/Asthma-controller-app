from sqlalchemy import select

from repositories.base_repository import BaseRepository
from repositories.orm_models import Reminder, UserLocation


class SettingsRepository(BaseRepository):
    def save_user_location(
        self, user_id: str, label: str, lat: float, lon: float
    ) -> None:
        existing = self.db.get(UserLocation, user_id)
        if existing:
            existing.city_label = label
            existing.lat = lat
            existing.lon = lon
        else:
            self.db.add(
                UserLocation(user_id=user_id, city_label=label, lat=lat, lon=lon)
            )

    def get_user_location(self, user_id: str):
        row = self.db.get(UserLocation, user_id)
        if row is None:
            return None
        return {"label": row.city_label, "lat": row.lat, "lon": row.lon}

    def upsert_reminder(self, user_id: str, hour: int, minute: int) -> None:
        existing = self.db.get(Reminder, user_id)
        if existing:
            existing.hour = hour
            existing.minute = minute
        else:
            self.db.add(
                Reminder(user_id=user_id, hour=hour, minute=minute, last_sent=None)
            )

    def get_reminder(self, user_id: str):
        row = self.db.get(Reminder, user_id)
        return (row.hour, row.minute) if row else None

    def get_all_reminders(self) -> list:
        rows = self.db.execute(
            select(Reminder.user_id, Reminder.hour, Reminder.minute, Reminder.last_sent)
        ).all()
        return [(r.user_id, r.hour, r.minute, r.last_sent) for r in rows]

    def mark_reminder_sent(self, user_id: str, date_str: str) -> None:
        reminder = self.db.get(Reminder, user_id)
        if reminder:
            reminder.last_sent = date_str
