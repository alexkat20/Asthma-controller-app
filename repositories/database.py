"""
Репозиторий основной БД Peak Flow: пользователи, препараты, показания, зоны, импорт файлов.

Это единственный слой, который знает SQL (через SQLAlchemy ORM) и структуру
таблиц users / medicine / taken_medicine / extra_info / readings. Сервисы
обращаются сюда, а не пишут SQL сами.

Бэкенд БД — SQLite (по умолчанию) или PostgreSQL, переключается переменной
окружения DB_BACKEND (см. repositories/db_engine.py) без изменений в коде.

Ключевые особенности (важно сохранить при дальнейших изменениях):
1. Зоны (зелёная/жёлтая/красная) считаются НЕ по последним 20 записям подряд,
   а как "personal best" (лучший результат) в скользящем окне по ДАТЕ
   (по умолчанию 90 дней) — это ближе к принятой методике пикфлоуметрии
   и не даёт одному плохому дню резко "обрушить" границы зон.
2. Импорт файлов не пытается вставить несуществующую в таблице readings
   колонку "Extra info" — это было причиной падения при загрузке xlsx/csv
   в самой первой версии бота.
3. Препараты, встреченные в файле, но отсутствующие в таблице medicine,
   создаются автоматически, а не приводят к KeyError.
4. Даты хранятся строками "%Y-%m-%d %H:%M:%S" (не DateTime) — формат
   лексикографически сортируется, поэтому сравнения "date >= ? AND date <= ?"
   работают одинаково на SQLite и PostgreSQL без каких-либо специфичных для
   диалекта SQL-функций (раньше здесь был SQLite-специфичный datetime('now', ?),
   который на Postgres просто не сработал бы).
"""

from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import bindparam, func, select, update
from sqlalchemy.orm import Session

from models.domain import ZoneThresholds
from repositories.db_engine import Base, SessionLocal, engine
from repositories.orm_models import ExtraInfo, Medicine, Reading, TakenMedicine, User

# Персональный рекорд считается по данным за этот период (в днях)
DEFAULT_ZONE_WINDOW_DAYS = 90

GREEN_RATIO = 0.8
YELLOW_RATIO = 0.5

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# В исходном формате файла (First try/Second try/.../Date) времени никогда нет —
# колонка Date строго "MM/DD/YYYY". Раньше таким записям молча ставилась полночь
# (00:00), из-за чего на графике они "прятались" в самое начало дня. Ставим 23:00 —
# ближе к вечерней записи (когда обычно и подводят итог дня), и при отрисовке
# графика с точным временем на оси X эти точки не будут визуально сливаться с
# записями, сделанными в начале дня.
DEFAULT_IMPORT_TIME = "23:00:00"

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


def get_connection() -> Session:
    """Возвращает новую сессию SQLAlchemy. Имя и контракт (commit()/close())
    сохранены от старого sqlite3.Connection специально, чтобы не переписывать
    полтора десятка мест в services/*, которые вызывают db.get_connection()."""
    return SessionLocal()


def init_db() -> None:
    """Создаёт все таблицы, если их ещё нет. Для продакшена предпочтителен
    `alembic upgrade head` (см. alembic/ и README) — init_db() остаётся как
    удобство для быстрого локального старта и не мешает Alembic: обе схемы
    идентичны (первая миграция сгенерирована с этой же ORM-схемы)."""
    Base.metadata.create_all(bind=engine)


def _to_date_str(value) -> str:
    if isinstance(value, str):
        return value
    return value.strftime(DATE_FORMAT)


def ensure_user(
    conn: Session, user_id: str, username=None, name=None, surname=None
) -> None:
    if conn.get(User, user_id) is None:
        conn.add(User(user_id=user_id, username=username, name=name, surname=surname))
    conn.commit()


def get_or_create_medicine_id(conn: Session, medicine_name: str, dose: str = "") -> int:
    existing = conn.execute(
        select(Medicine).where(Medicine.medicine_name.ilike(medicine_name))
    ).scalar_one_or_none()
    if existing:
        return existing.medicine_id

    medicine = Medicine(medicine_name=medicine_name, dose=dose)
    conn.add(medicine)
    conn.commit()
    conn.refresh(medicine)
    return medicine.medicine_id


def upsert_medicine(conn: Session, medicine_name: str, dose: str = "") -> None:
    """Добавляет препарат или обновляет дозу существующего (medicine_name уникален)."""
    existing = conn.execute(
        select(Medicine).where(Medicine.medicine_name == medicine_name)
    ).scalar_one_or_none()
    if existing:
        existing.dose = dose
    else:
        conn.add(Medicine(medicine_name=medicine_name, dose=dose))
    conn.commit()


def list_medicine_names(conn: Session) -> list:
    return list(conn.execute(select(Medicine.medicine_name)).scalars().all())


def list_medicines_with_doses(conn: Session) -> list:
    """Возвращает [(medicine_name, dose), ...] — для кнопок выбора препарата в диалоге."""
    rows = conn.execute(
        select(Medicine.medicine_name, Medicine.dose).order_by(Medicine.medicine_name)
    ).all()
    return [(r.medicine_name, r.dose) for r in rows]


def add_taken_medicine(
    conn: Session, medicine_id: int, user_id: str, doses: int, date_str: str
) -> None:
    conn.add(
        TakenMedicine(
            medicine_id=medicine_id, user_id=user_id, doses=doses, date=date_str
        )
    )


def add_extra_info(
    conn: Session,
    user_id: str,
    date_str: str,
    flags: dict,
    attacks_count: int | None = None,
    record_time: str | None = None,
) -> None:
    conn.add(
        ExtraInfo(
            user_id=user_id,
            date=date_str,
            sport=flags.get("sport", False),
            sickness=flags.get("sickness", False),
            stress=flags.get("stress", False),
            allergy=flags.get("allergy", False),
            flight=flags.get("flight", False),
            attacks_count=attacks_count,
            record_time=record_time,
        )
    )


def calculate_zone_thresholds(
    conn: Session,
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

    as_of_str = as_of_date.strftime(DATE_FORMAT)
    window_start_str = (as_of_date - timedelta(days=window_days)).strftime(DATE_FORMAT)

    personal_best = conn.execute(
        select(func.max(Reading.maximum)).where(
            Reading.user_id == user_id,
            Reading.maximum.isnot(None),
            Reading.date <= as_of_str,
            Reading.date >= window_start_str,
        )
    ).scalar_one_or_none()

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
    conn: Session,
    user_id: str,
    date,
    first_try: float,
    second_try: float,
    third_try: float,
) -> tuple:
    """Вставляет новую запись и сразу считает для неё зоны. Возвращает (id, thresholds, zone_name)."""
    maximum = max(first_try, second_try, third_try)
    date_str = _to_date_str(date)

    thresholds = calculate_zone_thresholds(
        conn, user_id, date, DEFAULT_ZONE_WINDOW_DAYS
    )
    if thresholds is None:
        thresholds = ZoneThresholds(
            personal_best=maximum,
            green_zone=round(maximum * GREEN_RATIO, 1),
            yellow_zone=round(maximum * YELLOW_RATIO, 1),
        )
    else:
        pb = max(thresholds.personal_best, maximum)
        thresholds = ZoneThresholds(
            personal_best=pb,
            green_zone=round(pb * GREEN_RATIO, 1),
            yellow_zone=round(pb * YELLOW_RATIO, 1),
        )

    reading = Reading(
        user_id=user_id,
        date=date_str,
        first_try=first_try,
        second_try=second_try,
        third_try=third_try,
        maximum=maximum,
        green_zone=thresholds.green_zone,
        yellow_zone=thresholds.yellow_zone,
        red_zone=thresholds.red_zone,
    )
    conn.add(reading)
    conn.commit()
    conn.refresh(reading)

    zone = classify_zone(maximum, thresholds)
    return reading.id, thresholds, zone


def recalculate_zones_for_user_history(
    conn: Session, user_id: str, window_days: int = DEFAULT_ZONE_WINDOW_DAYS
) -> int:
    """Пересчитывает green_zone/yellow_zone для ВСЕЙ истории пользователя (после импорта)."""
    rows = conn.execute(
        select(Reading.id, Reading.date, Reading.maximum)
        .where(Reading.user_id == user_id)
        .order_by(Reading.date)
    ).all()
    if not rows:
        return 0

    df = pd.DataFrame(rows, columns=["id", "date", "maximum"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    personal_best = df["maximum"].rolling(f"{window_days}D", min_periods=1).max()

    updates = []
    reset = df.reset_index()
    for idx, pb in zip(reset.index, personal_best.values):
        row_id = int(reset.iloc[idx]["id"])
        updates.append(
            {
                "b_id": row_id,
                "green_zone": round(pb * GREEN_RATIO, 1),
                "yellow_zone": round(pb * YELLOW_RATIO, 1),
                "red_zone": 0.0,
            }
        )

    if updates:
        conn.connection().execute(
            update(Reading)
            .where(Reading.id == bindparam("b_id"))
            .values(
                green_zone=bindparam("green_zone"),
                yellow_zone=bindparam("yellow_zone"),
                red_zone=bindparam("red_zone"),
            ),
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


def import_dataframe(conn: Session, df: pd.DataFrame, user_id: str) -> dict:
    """
    Импортирует датафрейм в ожидаемом формате: First try, Second try, Third try,
    Maximum, Date, <названия препаратов...>, Green/Yellow/Red Zone (игнорируются —
    пересчитываются), Extra info. Возвращает статистику импорта.
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

    for med_name in medicine_cols:
        get_or_create_medicine_id(conn, med_name)

    readings_inserted = 0
    doses_inserted = 0
    extra_info_inserted = 0

    for _, row in df.iterrows():
        date_str = row["Date"].strftime(f"%Y-%m-%d {DEFAULT_IMPORT_TIME}")

        first_try = row.get("First try")
        second_try = row.get("Second try")
        third_try = row.get("Third try")
        if pd.isna(first_try) or pd.isna(second_try) or pd.isna(third_try):
            continue

        maximum = (
            float(row["Maximum"])
            if "Maximum" in df.columns and not pd.isna(row.get("Maximum"))
            else max(first_try, second_try, third_try)
        )
        conn.add(
            Reading(
                user_id=user_id,
                date=date_str,
                first_try=float(first_try),
                second_try=float(second_try),
                third_try=float(third_try),
                maximum=maximum,
                green_zone=None,
                yellow_zone=None,
                red_zone=None,
            )
        )
        readings_inserted += 1

        for med_name in medicine_cols:
            doses = row.get(med_name)
            if pd.isna(doses) or doses == 0:
                continue
            medicine_id = get_or_create_medicine_id(conn, med_name)
            add_taken_medicine(conn, medicine_id, user_id, int(doses), date_str)
            doses_inserted += 1

        if "Extra info" in df.columns:
            flags = _parse_extra_info_cell(row.get("Extra info"))
            if any(flags.values()):
                add_extra_info(conn, user_id, date_str, flags)
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


# ---------------------------------------------------------------------------
# Выборки для аналитики/графиков/прогноза/рекомендаций/экспорта.
# Репозиторий отдаёт "сырые" DataFrame — вся агрегация/визуализация в сервисах.
# ---------------------------------------------------------------------------
def fetch_full_readings_df(
    conn: Session, user_id: str, start_str: str, end_str: str
) -> pd.DataFrame:
    """Полная выборка показаний (все колонки) за период — для экспорта в CSV
    (services/export_service.py), в отличие от fetch_readings_df, которая
    отдаёт только date+maximum для графиков/аналитики."""
    stmt = (
        select(
            Reading.date,
            Reading.first_try,
            Reading.second_try,
            Reading.third_try,
            Reading.maximum,
            Reading.green_zone,
            Reading.yellow_zone,
            Reading.red_zone,
        )
        .where(
            Reading.user_id == user_id,
            Reading.date >= start_str,
            Reading.date <= end_str,
        )
        .order_by(Reading.date)
    )
    return pd.DataFrame(
        conn.execute(stmt).all(),
        columns=[
            "date",
            "first_try",
            "second_try",
            "third_try",
            "maximum",
            "green_zone",
            "yellow_zone",
            "red_zone",
        ],
    )


def fetch_readings_df(
    conn: Session, user_id: str, start_str: str, end_str: str
) -> pd.DataFrame:
    stmt = (
        select(Reading.date, Reading.maximum)
        .where(
            Reading.user_id == user_id,
            Reading.maximum.isnot(None),
            Reading.date >= start_str,
            Reading.date <= end_str,
        )
        .order_by(Reading.date)
    )
    return pd.DataFrame(conn.execute(stmt).all(), columns=["date", "maximum"])


def fetch_flags_df(
    conn: Session, user_id: str, start_str: str, end_str: str
) -> pd.DataFrame:
    stmt = select(
        ExtraInfo.date,
        ExtraInfo.sport,
        ExtraInfo.sickness,
        ExtraInfo.stress,
        ExtraInfo.allergy,
        ExtraInfo.flight,
    ).where(
        ExtraInfo.user_id == user_id,
        ExtraInfo.date >= start_str,
        ExtraInfo.date <= end_str,
    )
    return pd.DataFrame(
        conn.execute(stmt).all(),
        columns=["date", "sport", "sickness", "stress", "allergy", "flight"],
    )


def fetch_extra_info_full_df(
    conn: Session, user_id: str, start_str: str, end_str: str
) -> pd.DataFrame:
    """Полная выборка extra_info (включая attacks_count/record_time) — для
    табличного отображения в чате (services/table_service.py). В отличие от
    fetch_flags_df, которая отдаёт только флаги состояния для прогноза/анализа."""
    stmt = select(
        ExtraInfo.date,
        ExtraInfo.sport,
        ExtraInfo.sickness,
        ExtraInfo.stress,
        ExtraInfo.allergy,
        ExtraInfo.flight,
        ExtraInfo.attacks_count,
        ExtraInfo.record_time,
    ).where(
        ExtraInfo.user_id == user_id,
        ExtraInfo.date >= start_str,
        ExtraInfo.date <= end_str,
    )
    return pd.DataFrame(
        conn.execute(stmt).all(),
        columns=[
            "date",
            "sport",
            "sickness",
            "stress",
            "allergy",
            "flight",
            "attacks_count",
            "record_time",
        ],
    )


def fetch_medicine_doses_df(
    conn: Session, user_id: str, start_str: str, end_str: str
) -> pd.DataFrame:
    stmt = (
        select(TakenMedicine.date, Medicine.medicine_name, TakenMedicine.doses)
        .join(Medicine, Medicine.medicine_id == TakenMedicine.medicine_id)
        .where(
            TakenMedicine.user_id == user_id,
            TakenMedicine.date >= start_str,
            TakenMedicine.date <= end_str,
        )
    )
    return pd.DataFrame(
        conn.execute(stmt).all(), columns=["date", "medicine_name", "doses"]
    )


def fetch_history_since_df(conn: Session, user_id: str, since_str: str) -> pd.DataFrame:
    """Вся история с определённой даты, без верхней границы — для прогноза (forecast_service.py)."""
    stmt = (
        select(Reading.date, Reading.maximum)
        .where(
            Reading.user_id == user_id,
            Reading.maximum.isnot(None),
            Reading.date >= since_str,
        )
        .order_by(Reading.date)
    )
    return pd.DataFrame(conn.execute(stmt).all(), columns=["date", "maximum"])


def fetch_flags_since_df(conn: Session, user_id: str, since_str: str) -> pd.DataFrame:
    stmt = select(
        ExtraInfo.date,
        ExtraInfo.sport,
        ExtraInfo.sickness,
        ExtraInfo.stress,
        ExtraInfo.allergy,
        ExtraInfo.flight,
    ).where(ExtraInfo.user_id == user_id, ExtraInfo.date >= since_str)
    return pd.DataFrame(
        conn.execute(stmt).all(),
        columns=["date", "sport", "sickness", "stress", "allergy", "flight"],
    )


def fetch_all_readings_with_zones_df(conn: Session, user_id: str) -> pd.DataFrame:
    """Вся история показаний с уже посчитанными на тот момент зонами — для recommend_service.py."""
    stmt = (
        select(Reading.date, Reading.maximum, Reading.green_zone, Reading.yellow_zone)
        .where(
            Reading.user_id == user_id,
            Reading.maximum.isnot(None),
            Reading.green_zone.isnot(None),
        )
        .order_by(Reading.date)
    )
    return pd.DataFrame(
        conn.execute(stmt).all(),
        columns=["date", "maximum", "green_zone", "yellow_zone"],
    )


def fetch_all_taken_medicine_with_names_df(conn: Session, user_id: str) -> pd.DataFrame:
    stmt = (
        select(TakenMedicine.date, Medicine.medicine_name)
        .join(Medicine, Medicine.medicine_id == TakenMedicine.medicine_id)
        .where(TakenMedicine.user_id == user_id)
    )
    return pd.DataFrame(conn.execute(stmt).all(), columns=["date", "medicine_name"])
