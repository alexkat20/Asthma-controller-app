"""
Семейный доступ для родителей/опекунов — только чтение.

Владелец данных выдаёт ссылку с токеном; тот, кто открыл её, попадает в чат
в режиме "только чтение", видит те же данные (показания, анализ, прогноз,
профиль, ACT, отчёт), но не может ничего изменить — ни записать показания,
ни поменять профиль/напоминания/город, ни пройти тест заново.

Технически токен — это альтернативный "user_id", который chat_service (см.
resolve_viewer) на каждом сообщении подменяет на настоящий user_id владельца
для ЧТЕНИЯ данных, но помечает сессию как read-only, чтобы заблокировать
операции записи.
"""

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
    """Возвращает (effective_user_id, is_read_only).

    Если user_id — это выданный ранее токен просмотра, подменяет его на
    user_id владельца и включает режим "только чтение". Иначе возвращает
    исходный user_id как есть (обычный, полноправный пользователь).
    """
    conn = get_connection()
    owner_user_id = family_repo.get_owner_by_token(conn, user_id)
    conn.close()
    if owner_user_id:
        return owner_user_id, True
    return user_id, False


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
