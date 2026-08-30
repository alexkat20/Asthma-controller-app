from repositories.base_repository import BaseRepository
from repositories.orm_models import User


class UserRepository(BaseRepository):
    def ensure_user(self, user_id: str, username=None, name=None, surname=None) -> None:
        if self.db.get(User, user_id) is None:
            self.db.add(
                User(user_id=user_id, username=username, name=name, surname=surname)
            )
            self.db.flush()
