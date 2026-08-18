import json

from sqlalchemy.orm import Session

from repositories.orm_models import ChatSession


def load_session(conn: Session, user_id: str) -> dict:
    row = conn.get(ChatSession, user_id)
    if row is None:
        return {}
    try:
        return json.loads(row.data)
    except (json.JSONDecodeError, TypeError):
        return {}


def save_session(conn: Session, user_id: str, session: dict, updated_at: str) -> None:
    payload = json.dumps(session, ensure_ascii=False)
    existing = conn.get(ChatSession, user_id)
    if existing:
        existing.data = payload
        existing.updated_at = updated_at
    else:
        conn.add(ChatSession(user_id=user_id, data=payload, updated_at=updated_at))
    conn.commit()
