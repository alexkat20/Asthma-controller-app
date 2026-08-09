"""
Репозиторий результатов теста контроля астмы (ACT-подобного опросника).

Сортировка "последний результат" — по id (autoincrement), а не по строке date:
при двух тестах в одну и ту же секунду (например, в тестах или если кто-то
пройдёт тест дважды подряд) сравнение строк даты даёт ничью, и SQLite не
гарантирует порядок при равенстве ключа сортировки — id монотонно растёт
с вставкой и однозначно отражает порядок прохождения тестов.
"""

import sqlite3


def ensure_act_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS act_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            date TEXT,
            answers TEXT,
            total_score INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS act_notify_state (
            user_id TEXT PRIMARY KEY,
            last_notified_date TEXT
        )
        """
    )


def save_act_result(
    conn: sqlite3.Connection,
    user_id: str,
    answers: list,
    total_score: int,
    date_str: str,
) -> None:
    ensure_act_table(conn)
    conn.execute(
        "INSERT INTO act_results (user_id, date, answers, total_score) VALUES (?, ?, ?, ?)",
        (user_id, date_str, ",".join(str(a) for a in answers), total_score),
    )
    conn.commit()


def get_last_act(conn: sqlite3.Connection, user_id: str):
    ensure_act_table(conn)
    row = conn.execute(
        "SELECT date, total_score FROM act_results WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return {"date": row[0], "total_score": row[1]}


def get_act_history(conn: sqlite3.Connection, user_id: str, limit: int = 12) -> list:
    ensure_act_table(conn)
    rows = conn.execute(
        "SELECT date, total_score FROM act_results WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [{"date": r[0], "total_score": r[1]} for r in rows]


def get_last_notified(conn: sqlite3.Connection, user_id: str):
    ensure_act_table(conn)
    row = conn.execute(
        "SELECT last_notified_date FROM act_notify_state WHERE user_id=?", (user_id,)
    ).fetchone()
    return row[0] if row else None


def mark_notified(conn: sqlite3.Connection, user_id: str, date_str: str) -> None:
    ensure_act_table(conn)
    conn.execute(
        """
        INSERT INTO act_notify_state (user_id, last_notified_date) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET last_notified_date = excluded.last_notified_date
        """,
        (user_id, date_str),
    )
    conn.commit()
