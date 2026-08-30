from datetime import datetime

from repositories import notification_repository


def push(user_id: str, text: str) -> None:
    notification_repository.push(
        user_id, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


def pop_all(user_id: str) -> list:
    return notification_repository.pop_all(user_id)
