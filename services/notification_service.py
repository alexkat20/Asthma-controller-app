"""
Очередь фоновых уведомлений (напоминания, ежедневный дайджест) — в памяти процесса.

Без Telegram push доставка идёт через поллинг: фронтенд периодически спрашивает
GET /api/notifications/{user_id}, а этот сервис отдаёт и очищает накопленные
сообщения для пользователя.
"""

import threading

_NOTIFICATIONS: dict = {}
_lock = threading.Lock()


def push(user_id: str, text: str) -> None:
    with _lock:
        _NOTIFICATIONS.setdefault(user_id, []).append(text)


def pop_all(user_id: str) -> list:
    with _lock:
        return _NOTIFICATIONS.pop(user_id, [])
