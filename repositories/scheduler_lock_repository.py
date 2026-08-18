from datetime import datetime, timedelta

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from repositories.orm_models import SchedulerLock

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOCK_ROW_ID = 1


def _ensure_lock_row(conn: Session) -> None:
    if conn.get(SchedulerLock, LOCK_ROW_ID) is None:
        conn.add(SchedulerLock(id=LOCK_ROW_ID, holder=None, expires_at=None))
        try:
            conn.commit()
        except Exception:
            conn.rollback()


def try_acquire(conn: Session, holder_id: str, lease_seconds: int = 90) -> bool:
    _ensure_lock_row(conn)

    now_str = datetime.now().strftime(DATE_FORMAT)
    expires_str = (datetime.now() + timedelta(seconds=lease_seconds)).strftime(DATE_FORMAT)

    result = conn.execute(
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
    conn.commit()
    return result.rowcount > 0


def release(conn: Session, holder_id: str) -> None:
    conn.execute(
        update(SchedulerLock)
        .where(SchedulerLock.id == LOCK_ROW_ID, SchedulerLock.holder == holder_id)
        .values(holder=None, expires_at=None)
        .execution_options(synchronize_session=False)
    )
    conn.commit()
