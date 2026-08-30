import secrets
from datetime import datetime

from repositories.unit_of_work import UnitOfWork


def generate_share_link(owner_user_id: str, label: str = "") -> str:
    token = secrets.token_urlsafe(12)
    with UnitOfWork() as uow:
        uow.family.create_share(
            token,
            owner_user_id,
            label.strip() or "Без названия",
            datetime.now().isoformat(),
        )
        uow.commit()
    return token


def resolve_viewer(user_id: str):
    with UnitOfWork() as uow:
        owner_user_id = uow.family.get_owner_by_token(user_id)
    if owner_user_id:
        return owner_user_id, True
    return user_id, False


def list_shares(owner_user_id: str) -> list:
    with UnitOfWork() as uow:
        return uow.family.list_shares(owner_user_id)


def list_shares_text(owner_user_id: str) -> str:
    shares = list_shares(owner_user_id)
    if not shares:
        return "Активных ссылок семейного доступа пока нет."
    lines = [f"«{s['label']}» — код: {s['token']}" for s in shares]
    return "Активные ссылки семейного доступа:\n" + "\n".join(lines)


def revoke(owner_user_id: str, token: str) -> str:
    with UnitOfWork() as uow:
        ok = uow.family.revoke_share(owner_user_id, token)
        uow.commit()
    return "Доступ отозван." if ok else "Не нашёл такую ссылку среди ваших."
