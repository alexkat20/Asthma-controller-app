"""
Очередь фоновых уведомлений (напоминания, ежедневный дайджест) — в БД,
см. repositories/notification_repository.py.

Без Telegram push доставка идёт через поллинг: фронтенд периодически спрашивает
GET /api/notifications/{user_id}, а этот сервис отдаёт и очищает накопленные
сообщения для пользователя. Раньше очередь жила в обычном dict в памяти
процесса — с несколькими воркерами/инстансами push из одного процесса не был
виден poll-у из другого (то же самое ограничение, что было у SESSIONS в
chat_service.py — см. подробности там). Планировщик (scheduler_worker.py)
теперь и вовсе отдельный процесс, поэтому это в любом случае обязательно.
"""

from datetime import datetime

from repositories import database as db
from repositories import notification_repository


def push(user_id: str, text: str) -> None:
    conn = db.get_connection()
    try:
        notification_repository.push(
            conn, user_id, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    finally:
        conn.close()


def pop_all(user_id: str) -> list:
    conn = db.get_connection()
    try:
        return notification_repository.pop_all(conn, user_id)
    finally:
        conn.close()
