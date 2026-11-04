from datetime import datetime, timedelta

from sqlalchemy import or_, update

from repositories.base_repository import BaseRepository
from repositories.orm_models import SchedulerLock

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOCK_ROW_ID = 1


class SchedulerLockRepository(BaseRepository):
    """Единственный репозиторий, чьи методы коммитят сами (self.db.commit()),
    в отличие от остальных.

    Это распределённый лок между несколькими процессами scheduler_worker.py —
    try_acquire() должен видеть и учитывать изменения, сделанные ДРУГИМ
    процессом между двумя своими шагами (создание строки лока гонкой, затем
    условный UPDATE), а не только то, что накопилось в рамках одного
    UnitOfWork. Откладывать коммит до внешней границы здесь нельзя — это
    сломало бы саму логику взаимоисключающего лока."""

    def _ensure_lock_row(self) -> None:
        if self.db.get(SchedulerLock, LOCK_ROW_ID) is None:
            self.db.add(SchedulerLock(id=LOCK_ROW_ID, holder=None, expires_at=None))
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()

    def try_acquire(self, holder_id: str, lease_seconds: int = 90) -> bool:
        self._ensure_lock_row()

        now_str = datetime.now().strftime(DATE_FORMAT)
        expires_str = (datetime.now() + timedelta(seconds=lease_seconds)).strftime(
            DATE_FORMAT
        )

        result = self.db.execute(
            update(SchedulerLock)
            .where(
                SchedulerLock.id == LOCK_ROW_ID,
                or_(
                    SchedulerLock.expires_at.is_(None),
                    SchedulerLock.expires_at < now_str,
                    SchedulerLock.holder == holder_id,
                ),
            )
            .values(holder=holder_id, expires_at=expires_str)
            .execution_options(synchronize_session=False)
        )
        self.db.commit()
        return result.rowcount > 0

    def release(self, holder_id: str) -> None:
        self.db.execute(
            update(SchedulerLock)
            .where(SchedulerLock.id == LOCK_ROW_ID, SchedulerLock.holder == holder_id)
            .values(holder=None, expires_at=None)
            .execution_options(synchronize_session=False)
        )
        self.db.commit()
