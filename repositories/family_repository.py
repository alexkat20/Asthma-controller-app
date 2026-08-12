"""
Репозиторий семейного доступа: read-only ссылки, которые владелец данных выдаёт
родственникам/опекунам. Токен — самостоятельный "просмотровый" идентификатор,
который на уровне chat_service подменяется на user_id владельца при чтении
данных, но никогда не даёт прав на запись (см. services/family_service.py).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from repositories.orm_models import FamilyAccess


def create_share(
    conn: Session, token: str, owner_user_id: str, label: str, created_at: str
) -> None:
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


def get_owner_by_token(conn: Session, token: str):
    row = conn.execute(
        select(FamilyAccess.owner_user_id).where(
            FamilyAccess.token == token, FamilyAccess.revoked.is_(False)
        )
    ).scalar_one_or_none()
    return row


def list_shares(conn: Session, owner_user_id: str) -> list:
    rows = conn.execute(
        select(FamilyAccess.token, FamilyAccess.label, FamilyAccess.created_at)
        .where(
            FamilyAccess.owner_user_id == owner_user_id, FamilyAccess.revoked.is_(False)
        )
        .order_by(FamilyAccess.created_at.desc())
    ).all()
    return [
        {"token": r.token, "label": r.label, "created_at": r.created_at} for r in rows
    ]


def revoke_share(conn: Session, owner_user_id: str, token: str) -> bool:
    row = conn.execute(
        select(FamilyAccess).where(
            FamilyAccess.token == token, FamilyAccess.owner_user_id == owner_user_id
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.revoked = True
    conn.commit()
    return True
