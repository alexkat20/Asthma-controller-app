from sqlalchemy import delete
from sqlalchemy.orm import Session

from repositories.orm_models import Notification


def push(conn: Session, user_id: str, message: str, created_at: str) -> None:
    conn.add(Notification(user_id=user_id, message=message, created_at=created_at))
    conn.commit()


def pop_all(conn: Session, user_id: str) -> list:
    result = conn.execute(
        delete(Notification)
        .where(Notification.user_id == user_id)
        .returning(Notification.message)
        .execution_options(synchronize_session=False)
    )
    messages = [row[0] for row in result]
    conn.commit()
    return messages
