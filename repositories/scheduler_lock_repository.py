"""
Блокировка планировщика (см. orm_models.SchedulerLock, scheduler_worker.py).

Захват — атомарный UPDATE с условием в WHERE и проверкой количества
затронутых строк, а не "прочитать -> проверить в Python -> записать" (у
последнего есть окно гонки: два процесса могут одновременно прочитать
"лок свободен" и оба посчитать, что взяли его). UPDATE ... WHERE выполняется
атомарно на уровне самой СУБД — так одинаково корректно работает и на
SQLite, и на PostgreSQL, без pg_advisory_lock или другых специфичных для
диалекта механизмов (важно, раз SQLite остаётся для быстрых прогонов тестов).
"""

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
            # Кто-то другой создал строку параллельно между get() и commit() —
            # не страшно, дальше просто работаем с уже существующей строкой.
            conn.rollback()


def try_acquire(conn: Session, holder_id: str, lease_seconds: int = 90) -> bool:
    """Пытается захватить (или продлить свою же) аренду лока. Возвращает True,
    если лок теперь у holder_id."""
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
    """Явно освобождает лок (например, при штатной остановке процесса).
    Не обязателен — аренда истечёт сама, но так следующий держатель не ждёт."""
    conn.execute(
        update(SchedulerLock)
        .where(SchedulerLock.id == LOCK_ROW_ID, SchedulerLock.holder == holder_id)
        .values(holder=None, expires_at=None)
        .execution_options(synchronize_session=False)
    )
    conn.commit()
