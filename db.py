"""
Модуль работы с базой данных Peak Flow бота.

Ключевые изменения по сравнению со старой версией (main.py):
1. Зоны (зелёная/жёлтая/красная) считаются НЕ по последним 20 записям подряд,
   а как "personal best" (лучший результат) в скользящем окне по ДАТЕ
   (по умолчанию 90 дней) — это ближе к принятой методике пикфлоуметрии
   и не даёт одному плохому дню резко "обрушить" границы зон.
2. Уже сохранённые исторические зоны не считаются заново на каждый чих:
   для новой записи считается на момент её даты, для импорта — один
   проход rolling-окном по всей истории.
3. Импорт файлов больше не пытается вставить несуществующую в таблице
   readings колонку "Extra info" (это было причиной падения при загрузке
   xlsx/csv в старой версии).
4. Препараты, встреченные в файле, но отсутствующие в таблице medicine,
   создаются автоматически, а не приводят к KeyError.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

DB_PATH = "peak_flow.db"

# Персональный рекорд считается по данным за этот период (в днях)
DEFAULT_ZONE_WINDOW_DAYS = 90

GREEN_RATIO = 0.8
YELLOW_RATIO = 0.5

# Известные флаги состояния + допустимые алиасы из старого формата файлов
EXTRA_INFO_FLAGS = ["sport", "sickness", "stress", "allergy", "flight"]
EXTRA_INFO_ALIASES = {
    "sick": "sickness",
    "sickness": "sickness",
    "sport": "sport",
    "спорт": "sport",
    "stress": "stress",
    "стресс": "stress",
    "allergy": "allergy",
    "аллергия": "allergy",
    "болезнь": "sickness",
    "болел": "sickness",
    "flight": "flight",
    "перелёт": "flight",
    "перелет": "flight",
}


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            name TEXT,
            surname TEXT,
            birth_date DATE
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS medicine (
            medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
            medicine_name TEXT UNIQUE,
            dose TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS taken_medicine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medicine_id INTEGER,
            user_id TEXT,
            doses INTEGER,
            date DATE,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(medicine_id) REFERENCES medicine(medicine_id)
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS extra_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            date DATE,
            sport BOOLEAN DEFAULT 0,
            sickness BOOLEAN DEFAULT 0,
            stress BOOLEAN DEFAULT 0,
            allergy BOOLEAN DEFAULT 0,
            flight BOOLEAN DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """
    )

    # ВАЖНО: без "Extra info" — этой колонки в readings больше нет.
    # Именно её наличие в readings_cols ломало импорт файлов в старой версии.
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            date DATE,
            first_try REAL,
            second_try REAL,
            third_try REAL,
            maximum REAL,
            green_zone REAL,
            yellow_zone REAL,
            red_zone REAL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """
    )

    conn.commit()
    conn.close()


def ensure_user(
    conn: sqlite3.Connection, user_id: str, username=None, name=None, surname=None
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, name, surname) VALUES (?, ?, ?, ?)",
        (user_id, username, name, surname),
    )
    conn.commit()


def get_or_create_medicine_id(
    conn: sqlite3.Connection, medicine_name: str, dose: str = ""
) -> int:
    c = conn.cursor()
    c.execute(
        "SELECT medicine_id FROM medicine WHERE medicine_name = ? COLLATE NOCASE",
        (medicine_name,),
    )
    row = c.fetchone()
    if row:
        return row[0]
    c.execute(
        "INSERT INTO medicine (medicine_name, dose) VALUES (?, ?)",
        (medicine_name, dose),
    )
    conn.commit()
    return c.lastrowid


@dataclass
class ZoneThresholds:
    personal_best: float
    green_zone: float  # нижняя граница зелёной зоны
    yellow_zone: float  # нижняя граница жёлтой зоны
    red_zone: float = 0.0  # нижняя граница красной зоны (всегда 0)


def calculate_zone_thresholds(
    conn: sqlite3.Connection,
    user_id: str,
    as_of_date,
    window_days: int = DEFAULT_ZONE_WINDOW_DAYS,
) -> ZoneThresholds:
    """
    Personal best = максимум Maximum за window_days дней ДО и ВКЛЮЧАЯ as_of_date.
    Если истории ещё нет (первая запись) — personal best = самой этой записи,
    то есть первая запись всегда попадёт в зелёную зону.
    """
    if isinstance(as_of_date, str):
        as_of_date = datetime.fromisoformat(as_of_date.split(" ")[0].replace("/", "-"))

    row = conn.execute(
        """
        SELECT MAX(maximum) FROM readings
        WHERE user_id = ?
          AND maximum IS NOT NULL
          AND date <= ?
          AND date >= datetime(?, ?)
        """,
        (
            user_id,
            as_of_date.isoformat(),
            as_of_date.isoformat(),
            f"-{window_days} days",
        ),
    ).fetchone()

    personal_best = row[0] if row and row[0] is not None else None
    if personal_best is None:
        return None

    return ZoneThresholds(
        personal_best=personal_best,
        green_zone=round(personal_best * GREEN_RATIO, 1),
        yellow_zone=round(personal_best * YELLOW_RATIO, 1),
        red_zone=0.0,
    )


def classify_zone(maximum: float, thresholds: ZoneThresholds) -> str:
    if thresholds is None:
        return "unknown"
    if maximum >= thresholds.green_zone:
        return "green"
    if maximum >= thresholds.yellow_zone:
        return "yellow"
    return "red"


def insert_reading(
    conn: sqlite3.Connection,
    user_id: str,
    date,
    first_try: float,
    second_try: float,
    third_try: float,
) -> tuple[int, ZoneThresholds, str]:
    """Вставляет новую запись и сразу считает для неё зоны. Возвращает (id, thresholds, zone_name)."""
    maximum = max(first_try, second_try, third_try)
    date_str = date if isinstance(date, str) else date.strftime("%Y-%m-%d %H:%M:%S")

    thresholds = calculate_zone_thresholds(
        conn, user_id, date, DEFAULT_ZONE_WINDOW_DAYS
    )
    # Если это первая запись пользователя, personal best = сама эта запись
    if thresholds is None:
        thresholds = ZoneThresholds(
            personal_best=maximum,
            green_zone=round(maximum * GREEN_RATIO, 1),
            yellow_zone=round(maximum * YELLOW_RATIO, 1),
        )
    else:
        # personal best должен учитывать и текущую запись
        pb = max(thresholds.personal_best, maximum)
        thresholds = ZoneThresholds(
            personal_best=pb,
            green_zone=round(pb * GREEN_RATIO, 1),
            yellow_zone=round(pb * YELLOW_RATIO, 1),
        )

    cur = conn.execute(
        """
        INSERT INTO readings (
            user_id, date, first_try, second_try, third_try, maximum,
            green_zone, yellow_zone, red_zone
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            date_str,
            first_try,
            second_try,
            third_try,
            maximum,
            thresholds.green_zone,
            thresholds.yellow_zone,
            thresholds.red_zone,
        ),
    )
    conn.commit()

    zone = classify_zone(maximum, thresholds)
    return cur.lastrowid, thresholds, zone


def recalculate_zones_for_user_history(
    conn: sqlite3.Connection, user_id: str, window_days: int = DEFAULT_ZONE_WINDOW_DAYS
) -> int:
    """
    Пересчитывает green_zone/yellow_zone для ВСЕЙ истории пользователя
    (используется после массового импорта). Возвращает число обновлённых строк.
    """
    df = pd.read_sql(
        "SELECT id, date, maximum FROM readings WHERE user_id = ? ORDER BY date",
        conn,
        params=(user_id,),
    )
    if df.empty:
        return 0

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    # rolling по времени: максимум Maximum за окно window_days дней, включая текущий день
    personal_best = df["maximum"].rolling(f"{window_days}D", min_periods=1).max()

    updates = []
    for (idx, row), pb in zip(df.reset_index().iterrows(), personal_best.values):
        row_id = df.reset_index().iloc[idx]["id"]
        green = round(pb * GREEN_RATIO, 1)
        yellow = round(pb * YELLOW_RATIO, 1)
        updates.append((green, yellow, 0.0, int(row_id)))

    conn.executemany(
        "UPDATE readings SET green_zone = ?, yellow_zone = ?, red_zone = ? WHERE id = ?",
        updates,
    )
    conn.commit()
    return len(updates)


def _parse_extra_info_cell(cell: str) -> dict:
    """'Sport, Stress' / 'sick' / 'Аллергия' -> {'sport': True, 'stress': True, ...}"""
    flags = {f: False for f in EXTRA_INFO_FLAGS}
    if not cell or (isinstance(cell, float) and pd.isna(cell)):
        return flags
    tokens = [t.strip().lower() for t in str(cell).split(",") if t.strip()]
    for token in tokens:
        mapped = EXTRA_INFO_ALIASES.get(token)
        if mapped:
            flags[mapped] = True
    return flags


def import_dataframe(conn: sqlite3.Connection, df: pd.DataFrame, user_id: str) -> dict:
    """
    Импортирует датафрейм в ожидаемом формате (как в исходном xlsx пользователя):
    First try, Second try, Third try, Maximum, Date, <названия препаратов...>,
    Green Zone, Yellow Zone, Red Zone (игнорируются — пересчитываются), Extra info.

    Возвращает статистику импорта.
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    required = {"First try", "Second try", "Third try", "Date"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"В файле не хватает колонок: {', '.join(sorted(missing))}")

    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    bad_dates = df["Date"].isna().sum()
    df = df.dropna(subset=["Date"])

    known_non_medicine_cols = {
        "First try",
        "Second try",
        "Third try",
        "Maximum",
        "Date",
        "Green Zone",
        "Yellow Zone",
        "Red Zone",
        "Extra info",
    }
    medicine_cols = [c for c in df.columns if c not in known_non_medicine_cols]

    # Гарантируем, что все встреченные препараты есть в таблице medicine
    for med_name in medicine_cols:
        get_or_create_medicine_id(conn, med_name)

    readings_inserted = 0
    doses_inserted = 0
    extra_info_inserted = 0

    for _, row in df.iterrows():
        date_str = row["Date"].strftime("%Y-%m-%d 00:00:00")

        first_try = row.get("First try")
        second_try = row.get("Second try")
        third_try = row.get("Third try")
        if pd.isna(first_try) or pd.isna(second_try) or pd.isna(third_try):
            continue

        conn.execute(
            """
            INSERT INTO readings (
                user_id, date, first_try, second_try, third_try, maximum,
                green_zone, yellow_zone, red_zone
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (
                user_id,
                date_str,
                float(first_try),
                float(second_try),
                float(third_try),
                float(row["Maximum"])
                if "Maximum" in df.columns and not pd.isna(row.get("Maximum"))
                else max(first_try, second_try, third_try),
            ),
        )
        readings_inserted += 1

        for med_name in medicine_cols:
            doses = row.get(med_name)
            if pd.isna(doses) or doses == 0:
                continue
            medicine_id = get_or_create_medicine_id(conn, med_name)
            conn.execute(
                "INSERT INTO taken_medicine (medicine_id, user_id, doses, date) VALUES (?, ?, ?, ?)",
                (medicine_id, user_id, int(doses), date_str),
            )
            doses_inserted += 1

        if "Extra info" in df.columns:
            flags = _parse_extra_info_cell(row.get("Extra info"))
            if any(flags.values()):
                conn.execute(
                    """
                    INSERT INTO extra_info (user_id, date, sport, sickness, stress, allergy, flight)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        date_str,
                        flags["sport"],
                        flags["sickness"],
                        flags["stress"],
                        flags["allergy"],
                        flags["flight"],
                    ),
                )
                extra_info_inserted += 1

    conn.commit()

    updated_zone_rows = recalculate_zones_for_user_history(conn, user_id)

    return {
        "rows_in_file": len(df),
        "readings_inserted": readings_inserted,
        "doses_inserted": doses_inserted,
        "extra_info_inserted": extra_info_inserted,
        "zone_rows_recalculated": updated_zone_rows,
        "bad_dates_skipped": int(bad_dates),
    }
