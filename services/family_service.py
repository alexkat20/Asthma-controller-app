import secrets
from datetime import datetime

from repositories import family_repository as family_repo
from repositories.database import get_connection


def generate_share_link(owner_user_id: str, label: str = "") -> str:
    token = secrets.token_urlsafe(12)
    conn = get_connection()
    family_repo.create_share(
        conn,
        token,
        owner_user_id,
        label.strip() or "Без названия",
        datetime.now().isoformat(),
    )
    conn.close()
    return token


def resolve_viewer(user_id: str):
    conn = get_connection()
    owner_user_id = family_repo.get_owner_by_token(conn, user_id)
    conn.close()
    if owner_user_id:
        return owner_user_id, True
    return user_id, False


def list_shares(owner_user_id: str) -> list:
    conn = get_connection()
    shares = family_repo.list_shares(conn, owner_user_id)
    conn.close()
    return shares


def list_shares_text(owner_user_id: str) -> str:
    conn = get_connection()
    shares = family_repo.list_shares(conn, owner_user_id)
    conn.close()
    if not shares:
        return "Активных ссылок семейного доступа пока нет."
    lines = [f"«{s['label']}» — код: {s['token']}" for s in shares]
    return "Активные ссылки семейного доступа:\n" + "\n".join(lines)


def revoke(owner_user_id: str, token: str) -> str:
    conn = get_connection()
    ok = family_repo.revoke_share(conn, owner_user_id, token)
    conn.close()
    return "Доступ отозван." if ok else "Не нашёл такую ссылку среди ваших."
