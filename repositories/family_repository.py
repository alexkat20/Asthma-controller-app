"""
Репозиторий семейного доступа: read-only ссылки, которые владелец данных выдаёт
родственникам/опекунам. Токен — самостоятельный "просмотровый" идентификатор,
который на уровне chat_service подменяется на user_id владельца при чтении
данных, но никогда не даёт прав на запись (см. services/family_service.py).
"""

import sqlite3


def ensure_family_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS family_access (
            token TEXT PRIMARY KEY,
            owner_user_id TEXT,
            label TEXT,
            created_at TEXT,
            revoked BOOLEAN DEFAULT 0
        )
        """
    )


def create_share(
    conn: sqlite3.Connection,
    token: str,
    owner_user_id: str,
    label: str,
    created_at: str,
) -> None:
    ensure_family_table(conn)
    conn.execute(
        "INSERT INTO family_access (token, owner_user_id, label, created_at, revoked) VALUES (?, ?, ?, ?, 0)",
        (token, owner_user_id, label, created_at),
    )
    conn.commit()


def get_owner_by_token(conn: sqlite3.Connection, token: str):
    ensure_family_table(conn)
    row = conn.execute(
        "SELECT owner_user_id FROM family_access WHERE token = ? AND revoked = 0",
        (token,),
    ).fetchone()
    return row[0] if row else None


def list_shares(conn: sqlite3.Connection, owner_user_id: str) -> list:
    ensure_family_table(conn)
    rows = conn.execute(
        "SELECT token, label, created_at FROM family_access WHERE owner_user_id = ? AND revoked = 0 ORDER BY created_at DESC",
        (owner_user_id,),
    ).fetchall()
    return [{"token": r[0], "label": r[1], "created_at": r[2]} for r in rows]


def revoke_share(conn: sqlite3.Connection, owner_user_id: str, token: str) -> bool:
    ensure_family_table(conn)
    cur = conn.execute(
        "UPDATE family_access SET revoked = 1 WHERE token = ? AND owner_user_id = ?",
        (token, owner_user_id),
    )
    conn.commit()
    return cur.rowcount > 0
