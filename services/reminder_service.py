"""
Напоминания: команда «напоминание HH:MM» + фоновый планировщик, который раз в
минуту проверяет, кому пора отправить утренний дайджест (прогноз + пыльца).

Без Telegram push уведомление кладётся в очередь (notification_service), а
забирает её фронтенд поллингом.
"""

import re
import threading
import time as time_module
from datetime import datetime

from repositories import settings_repository as settings_repo
from repositories.database import get_connection
from repositories.profile_repository import get_profile
from services import (
    act_service,
    allergy_service,
    forecast_service,
    notification_service,
)
from utils.formatting import ZONE_RU


def handle_reminder_command(user_id: str, text: str) -> str:
    conn = get_connection()
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        settings_repo.upsert_reminder(conn, user_id, hour, minute)
        conn.close()
        return f"⏰ Ежедневное напоминание установлено на {hour:02d}:{minute:02d}."

    row = settings_repo.get_reminder(conn, user_id)
    conn.close()
    if row:
        return f"⏰ Сейчас напоминание установлено на {row[0]:02d}:{row[1]:02d}. Чтобы изменить — напишите, например, «напоминание 08:30»."
    return "У вас ещё нет напоминания. Установите его, например: «напоминание 09:00»."


def _send_daily_digest(conn, user_id: str) -> None:
    today = forecast_service.forecast_today(conn, user_id)
    if today is None:
        msg = "📢 Не забудьте записать сегодняшние показания пикфлоуметра!"
    else:
        msg = (
            f"📢 Доброе утро! Ожидаемый пикфлоу сегодня: ~{today['predicted_value']:.0f} "
            f"({ZONE_RU[today['zone']]}). Сделайте замер и сравните с прогнозом."
        )

    loc = settings_repo.get_user_location(conn, user_id)
    if loc is not None:
        profile = get_profile(user_id)
        user_allergens = profile["allergies"] if profile else None
        pollen = allergy_service.get_today_pollen(loc["lat"], loc["lon"])
        pollen_summary = allergy_service.summarize_pollen(pollen, user_allergens)
        msg += f"\n\n📍 {loc['label']}\n{pollen_summary}"

    notification_service.push(user_id, msg)


def _check_reminders() -> None:
    conn = get_connection()
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    for user_id, hour, minute, last_sent in settings_repo.get_all_reminders(conn):
        if now.hour == hour and now.minute == minute and last_sent != today_str:
            _send_daily_digest(conn, user_id)
            settings_repo.mark_reminder_sent(conn, user_id, today_str)
    conn.commit()
    conn.close()


def _scheduler_loop() -> None:
    while True:
        try:
            _check_reminders()
        except Exception as exc:  # фоновый поток не должен падать целиком из-за одной ошибки
            print(f"[scheduler] ошибка (напоминания): {exc}")
        try:
            act_service.check_and_notify_due_users()
        except Exception as exc:
            print(f"[scheduler] ошибка (ACT): {exc}")
        time_module.sleep(60)


def start_scheduler() -> None:
    threading.Thread(target=_scheduler_loop, daemon=True).start()
