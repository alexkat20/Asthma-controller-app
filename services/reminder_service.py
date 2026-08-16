"""
Напоминания: команда «напоминание HH:MM» + проверка (check_reminders), кому
пора отправить утренний дайджест (прогноз + пыльца).

Сама периодичность («раз в минуту, для всех пользователей») теперь не здесь —
это делает отдельный процесс scheduler_worker.py, вызывающий check_reminders()
и act_service.check_and_notify_due_users() по таймеру. Раньше это был
threading.Thread внутри веб-процесса — с несколькими воркерами/инстансами
получили бы N параллельных планировщиков и N уведомлений вместо одного.

Без Telegram push уведомление кладётся в очередь (notification_service), а
забирает её фронтенд поллингом.
"""

import re
from datetime import datetime

from repositories import settings_repository as settings_repo
from repositories.database import get_connection
from repositories.profile_repository import get_profile
from services import allergy_service, forecast_service, notification_service
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


def check_reminders() -> None:
    """Вызывается из scheduler_worker.py по таймеру (раньше был приватным
    _check_reminders, вызывавшимся только из потока внутри этого же модуля —
    теперь легитимно вызывается извне, поэтому без ведущего подчёркивания)."""
    conn = get_connection()
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    for user_id, hour, minute, last_sent in settings_repo.get_all_reminders(conn):
        if now.hour == hour and now.minute == minute and last_sent != today_str:
            _send_daily_digest(conn, user_id)
            settings_repo.mark_reminder_sent(conn, user_id, today_str)
    conn.commit()
    conn.close()
