from sqlalchemy import delete

from repositories.base_repository import BaseRepository
from repositories.orm_models import Notification


class NotificationRepository(BaseRepository):
    def push(self, user_id: str, message: str, created_at: str) -> None:
        self.db.add(
            Notification(user_id=user_id, message=message, created_at=created_at)
        )

    def pop_all(self, user_id: str) -> list:
        result = self.db.execute(
            delete(Notification)
            .where(Notification.user_id == user_id)
            .returning(Notification.message)
            .execution_options(synchronize_session=False)
        )
        return [row[0] for row in result]
