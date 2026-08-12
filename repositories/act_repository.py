"""
Репозиторий результатов теста контроля астмы (ACT-подобного опросника).

Сортировка "последний результат" — по id (autoincrement), а не по строке date:
при двух тестах в одну и ту же секунду (например, в тестах или если кто-то
пройдёт тест дважды подряд) сравнение строк даты даёт ничью, и ни SQLite, ни
PostgreSQL не гарантируют порядок при равенстве ключа сортировки — id
монотонно растёт с вставкой и однозначно отражает порядок прохождения тестов.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from repositories.orm_models import ActNotifyState, ActResult


def save_act_result(
    conn: Session, user_id: str, answers: list, total_score: int, date_str: str
) -> None:
    conn.add(
        ActResult(
            user_id=user_id,
            date=date_str,
            answers=",".join(str(a) for a in answers),
            total_score=total_score,
        )
    )
    conn.commit()


def get_last_act(conn: Session, user_id: str):
    row = conn.execute(
        select(ActResult.date, ActResult.total_score)
        .where(ActResult.user_id == user_id)
        .order_by(ActResult.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return {"date": row.date, "total_score": row.total_score}


def get_act_history(conn: Session, user_id: str, limit: int = 12) -> list:
    rows = conn.execute(
        select(ActResult.date, ActResult.total_score)
        .where(ActResult.user_id == user_id)
        .order_by(ActResult.id.desc())
        .limit(limit)
    ).all()
    return [{"date": r.date, "total_score": r.total_score} for r in rows]


def get_last_notified(conn: Session, user_id: str):
    row = conn.get(ActNotifyState, user_id)
    return row.last_notified_date if row else None


def mark_notified(conn: Session, user_id: str, date_str: str) -> None:
    existing = conn.get(ActNotifyState, user_id)
    if existing:
        existing.last_notified_date = date_str
    else:
        conn.add(ActNotifyState(user_id=user_id, last_notified_date=date_str))
    conn.commit()
