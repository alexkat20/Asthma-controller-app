from sqlalchemy import select

from repositories.base_repository import BaseRepository
from repositories.orm_models import ActNotifyState, ActResult


class ActRepository(BaseRepository):
    def save_act_result(
        self, user_id: str, answers: list, total_score: int, date_str: str
    ) -> None:
        self.db.add(
            ActResult(
                user_id=user_id,
                date=date_str,
                answers=",".join(str(a) for a in answers),
                total_score=total_score,
            )
        )

    def get_last_act(self, user_id: str):
        row = self.db.execute(
            select(ActResult.date, ActResult.total_score)
            .where(ActResult.user_id == user_id)
            .order_by(ActResult.id.desc())
            .limit(1)
        ).first()
        if row is None:
            return None
        return {"date": row.date, "total_score": row.total_score}

    def get_act_history(self, user_id: str, limit: int = 12) -> list:
        rows = self.db.execute(
            select(ActResult.date, ActResult.total_score)
            .where(ActResult.user_id == user_id)
            .order_by(ActResult.id.desc())
            .limit(limit)
        ).all()
        return [{"date": r.date, "total_score": r.total_score} for r in rows]

    def get_last_notified(self, user_id: str):
        row = self.db.get(ActNotifyState, user_id)
        return row.last_notified_date if row else None

    def mark_notified(self, user_id: str, date_str: str) -> None:
        existing = self.db.get(ActNotifyState, user_id)
        if existing:
            existing.last_notified_date = date_str
        else:
            self.db.add(ActNotifyState(user_id=user_id, last_notified_date=date_str))
