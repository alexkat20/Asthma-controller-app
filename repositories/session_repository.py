import json

from repositories.base_repository import BaseRepository
from repositories.orm_models import ChatSession


class SessionRepository(BaseRepository):
    def load_session(self, user_id: str) -> dict:
        row = self.db.get(ChatSession, user_id)
        if row is None:
            return {}
        try:
            return json.loads(row.data)
        except (json.JSONDecodeError, TypeError):
            return {}

    def save_session(self, user_id: str, session: dict, updated_at: str) -> None:
        payload = json.dumps(session, ensure_ascii=False)
        existing = self.db.get(ChatSession, user_id)
        if existing:
            existing.data = payload
            existing.updated_at = updated_at
        else:
            self.db.add(
                ChatSession(user_id=user_id, data=payload, updated_at=updated_at)
            )
