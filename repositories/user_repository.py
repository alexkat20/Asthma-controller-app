from sqlalchemy.orm import Session

from repositories.db_engine import get_session
from repositories.orm_models import User


def _ensure_user(
    conn: Session, user_id: str, username=None, name=None, surname=None
) -> None:
    if conn.get(User, user_id) is None:
        conn.add(User(user_id=user_id, username=username, name=name, surname=surname))
        conn.flush()


def ensure_user(user_id: str, username=None, name=None, surname=None) -> None:
    conn = get_session()
    try:
        _ensure_user(conn, user_id, username, name, surname)
        conn.commit()
    finally:
        conn.close()
