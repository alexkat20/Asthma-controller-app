from sqlalchemy import select

from repositories.db_engine import get_session
from repositories.orm_models import ActNotifyState, ActResult


def save_act_result(
    user_id: str, answers: list, total_score: int, date_str: str
) -> None:
    conn = get_session()
    try:
        conn.add(
            ActResult(
                user_id=user_id,
                date=date_str,
                answers=",".join(str(a) for a in answers),
                total_score=total_score,
            )
        )
        conn.commit()
    finally:
        conn.close()


def get_last_act(user_id: str):
    conn = get_session()
    try:
        row = conn.execute(
            select(ActResult.date, ActResult.total_score)
            .where(ActResult.user_id == user_id)
            .order_by(ActResult.id.desc())
            .limit(1)
        ).first()
        if row is None:
            return None
        return {"date": row.date, "total_score": row.total_score}
    finally:
        conn.close()


def get_act_history(user_id: str, limit: int = 12) -> list:
    conn = get_session()
    try:
        rows = conn.execute(
            select(ActResult.date, ActResult.total_score)
            .where(ActResult.user_id == user_id)
            .order_by(ActResult.id.desc())
            .limit(limit)
        ).all()
        return [{"date": r.date, "total_score": r.total_score} for r in rows]
    finally:
        conn.close()


def get_last_notified(user_id: str):
    conn = get_session()
    try:
        row = conn.get(ActNotifyState, user_id)
        return row.last_notified_date if row else None
    finally:
        conn.close()


def mark_notified(user_id: str, date_str: str) -> None:
    conn = get_session()
    try:
        existing = conn.get(ActNotifyState, user_id)
        if existing:
            existing.last_notified_date = date_str
        else:
            conn.add(ActNotifyState(user_id=user_id, last_notified_date=date_str))
        conn.commit()
    finally:
        conn.close()
