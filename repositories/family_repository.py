from sqlalchemy import select

from repositories.db_engine import get_session
from repositories.orm_models import FamilyAccess


def create_share(token: str, owner_user_id: str, label: str, created_at: str) -> None:
    conn = get_session()
    try:
        conn.add(
            FamilyAccess(
                token=token,
                owner_user_id=owner_user_id,
                label=label,
                created_at=created_at,
                revoked=False,
            )
        )
        conn.commit()
    finally:
        conn.close()


def get_owner_by_token(token: str):
    conn = get_session()
    try:
        return conn.execute(
            select(FamilyAccess.owner_user_id).where(
                FamilyAccess.token == token, FamilyAccess.revoked.is_(False)
            )
        ).scalar_one_or_none()
    finally:
        conn.close()


def list_shares(owner_user_id: str) -> list:
    conn = get_session()
    try:
        rows = conn.execute(
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
    finally:
        conn.close()


def revoke_share(owner_user_id: str, token: str) -> bool:
    conn = get_session()
    try:
        row = conn.execute(
            select(FamilyAccess).where(
                FamilyAccess.token == token,
                FamilyAccess.owner_user_id == owner_user_id,
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.revoked = True
        conn.commit()
        return True
    finally:
        conn.close()
