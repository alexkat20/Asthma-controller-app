import json

from repositories.db_engine import get_session
from repositories.orm_models import ChatSession


def load_session(user_id: str) -> dict:
    conn = get_session()
    try:
        row = conn.get(ChatSession, user_id)
        if row is None:
            return {}
        try:
            return json.loads(row.data)
        except (json.JSONDecodeError, TypeError):
            return {}
    finally:
        conn.close()


def save_session(user_id: str, session: dict, updated_at: str) -> None:
    conn = get_session()
    try:
        payload = json.dumps(session, ensure_ascii=False)
        existing = conn.get(ChatSession, user_id)
        if existing:
            existing.data = payload
            existing.updated_at = updated_at
        else:
            conn.add(ChatSession(user_id=user_id, data=payload, updated_at=updated_at))
        conn.commit()
    finally:
        conn.close()
