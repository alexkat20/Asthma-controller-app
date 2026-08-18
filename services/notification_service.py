from datetime import datetime

from repositories import database as db
from repositories import notification_repository


def push(user_id: str, text: str) -> None:
    conn = db.get_connection()
    try:
        notification_repository.push(
            conn, user_id, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    finally:
        conn.close()


def pop_all(user_id: str) -> list:
    conn = db.get_connection()
    try:
        return notification_repository.pop_all(conn, user_id)
    finally:
        conn.close()
