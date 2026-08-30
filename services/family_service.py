import secrets
from datetime import datetime

from repositories import family_repository as family_repo


def generate_share_link(owner_user_id: str, label: str = "") -> str:
    token = secrets.token_urlsafe(12)
    family_repo.create_share(
        token,
        owner_user_id,
        label.strip() or "Без названия",
        datetime.now().isoformat(),
    )
    return token


def resolve_viewer(user_id: str):
    owner_user_id = family_repo.get_owner_by_token(user_id)
    if owner_user_id:
        return owner_user_id, True
    return user_id, False


def list_shares(owner_user_id: str) -> list:
    return family_repo.list_shares(owner_user_id)


def list_shares_text(owner_user_id: str) -> str:
    shares = family_repo.list_shares(owner_user_id)
    if not shares:
        return "Активных ссылок семейного доступа пока нет."
    lines = [f"«{s['label']}» — код: {s['token']}" for s in shares]
    return "Активные ссылки семейного доступа:\n" + "\n".join(lines)


def revoke(owner_user_id: str, token: str) -> str:
    ok = family_repo.revoke_share(owner_user_id, token)
    return "Доступ отозван." if ok else "Не нашёл такую ссылку среди ваших."
