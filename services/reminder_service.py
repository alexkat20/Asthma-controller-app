import re
from datetime import datetime

from repositories.unit_of_work import UnitOfWork
from services import allergy_service, forecast_service, notification_service
from utils.formatting import ZONE_RU


def handle_reminder_command(user_id: str, text: str) -> str:
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        with UnitOfWork() as uow:
            uow.settings.upsert_reminder(user_id, hour, minute)
            uow.commit()
        return f"⏰ Ежедневное напоминание установлено на {hour:02d}:{minute:02d}."

    with UnitOfWork() as uow:
        row = uow.settings.get_reminder(user_id)
    if row:
        return f"⏰ Сейчас напоминание установлено на {row[0]:02d}:{row[1]:02d}. Чтобы изменить — напишите, например, «напоминание 08:30»."
    return "У вас ещё нет напоминания. Установите его, например: «напоминание 09:00»."


def _send_daily_digest(user_id: str) -> None:
    today = forecast_service.forecast_today(user_id, period="morning")
    if today is None:
        msg = "📢 Не забудьте записать сегодняшние показания пикфлоуметра!"
    else:
        msg = (
            f"📢 Доброе утро! Ожидаемый утренний пикфлоу сегодня: ~{today['predicted_value']:.0f} "
            f"({ZONE_RU[today['zone']]}). Сделайте замер и сравните с прогнозом."
        )

    with UnitOfWork() as uow:
        loc = uow.settings.get_user_location(user_id)
        profile = uow.profiles.get_profile(user_id) if loc is not None else None

    if loc is not None:
        user_allergens = profile["allergies"] if profile else None
        pollen = allergy_service.get_today_pollen(loc["lat"], loc["lon"])
        pollen_summary = allergy_service.summarize_pollen(pollen, user_allergens)
        msg += f"\n\n📍 {loc['label']}\n{pollen_summary}"

    notification_service.push(user_id, msg)


def check_reminders() -> None:
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    with UnitOfWork() as uow:
        reminders = uow.settings.get_all_reminders()
    for user_id, hour, minute, last_sent in reminders:
        if now.hour == hour and now.minute == minute and last_sent != today_str:
            _send_daily_digest(user_id)
            with UnitOfWork() as uow:
                uow.settings.mark_reminder_sent(user_id, today_str)
                uow.commit()
