from sqlalchemy import select

from repositories.base_repository import BaseRepository
from repositories.orm_models import FamilyAccess


class FamilyRepository(BaseRepository):
    def create_share(
        self, token: str, owner_user_id: str, label: str, created_at: str
    ) -> None:
        self.db.add(
            FamilyAccess(
                token=token,
                owner_user_id=owner_user_id,
                label=label,
                created_at=created_at,
                revoked=False,
            )
        )

    def get_owner_by_token(self, token: str):
        return self.db.execute(
            select(FamilyAccess.owner_user_id).where(
                FamilyAccess.token == token, FamilyAccess.revoked.is_(False)
            )
        ).scalar_one_or_none()

    def list_shares(self, owner_user_id: str) -> list:
        rows = self.db.execute(
            select(FamilyAccess.token, FamilyAccess.label, FamilyAccess.created_at)
            .where(
                FamilyAccess.owner_user_id == owner_user_id,
                FamilyAccess.revoked.is_(False),
            )
            .order_by(FamilyAccess.created_at.desc())
        ).all()
        return [
            {"token": r.token, "label": r.label, "created_at": r.created_at}
            for r in rows
        ]

    def revoke_share(self, owner_user_id: str, token: str) -> bool:
        row = self.db.execute(
            select(FamilyAccess).where(
                FamilyAccess.token == token,
                FamilyAccess.owner_user_id == owner_user_id,
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.revoked = True
        return True
