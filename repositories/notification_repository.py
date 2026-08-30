from sqlalchemy import delete

from repositories.db_engine import get_session
from repositories.orm_models import Notification


def push(user_id: str, message: str, created_at: str) -> None:
    conn = get_session()
    try:
        conn.add(Notification(user_id=user_id, message=message, created_at=created_at))
        conn.commit()
    finally:
        conn.close()


def pop_all(user_id: str) -> list:
    conn = get_session()
    try:
        result = conn.execute(
            delete(Notification)
            .where(Notification.user_id == user_id)
            .returning(Notification.message)
            .execution_options(synchronize_session=False)
        )
        messages = [row[0] for row in result]
        conn.commit()
        return messages
    finally:
        conn.close()
