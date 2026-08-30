from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import bindparam, func, select, update

from models.domain import (
    GREEN_RATIO,
    YELLOW_RATIO,
    ZoneThresholds,
    classify_zone,
    thresholds_from_personal_best,
)
from repositories.base_repository import BaseRepository
from repositories.extra_info_repository import EXTRA_INFO_FLAGS, ExtraInfoRepository
from repositories.medicine_repository import MedicineRepository
from repositories.orm_models import Reading
from repositories.user_repository import UserRepository
from utils.dates import classify_period

# Персональный рекорд считается по данным за этот период (в днях)
DEFAULT_ZONE_WINDOW_DAYS = 90

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_IMPORT_TIME = "23:00:00"

_EXTRA_INFO_ALIASES = {
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
    "weather": "weather",
    "погода": "weather",
    "smoke": "smoke",
    "дым": "smoke",
    "strong_smells": "strong_smells",
    "запахи": "strong_smells",
    "pets": "pets",
    "животные": "pets",
    "dust": "dust",
    "пыль": "dust",
    "menstrual_cycle": "menstrual_cycle",
    "менструация": "menstrual_cycle",
    "dyspnea": "dyspnea",
    "одышка": "dyspnea",
    "cough": "cough",
    "кашель": "cough",
    "wheezing": "wheezing",
    "хрипы": "wheezing",
    "chest_tightness": "chest_tightness",
    "заложенность": "chest_tightness",
    "nocturnal_symptoms": "nocturnal_symptoms",
    "ночные симптомы": "nocturnal_symptoms",
}


def _to_date_str(value) -> str:
    if isinstance(value, str):
        return value
    return value.strftime(DATE_FORMAT)


def _parse_extra_info_cell(cell: str) -> dict:
    flags = {f: False for f in EXTRA_INFO_FLAGS}
    if not cell or (isinstance(cell, float) and pd.isna(cell)):
        return flags
    tokens = [t.strip().lower() for t in str(cell).split(",") if t.strip()]
    for token in tokens:
        mapped = _EXTRA_INFO_ALIASES.get(token)
        if mapped:
            flags[mapped] = True
    return flags


class ReadingRepository(BaseRepository):
    def calculate_zone_thresholds(
        self,
        user_id: str,
        as_of_date,
        window_days: int = DEFAULT_ZONE_WINDOW_DAYS,
    ) -> ZoneThresholds | None:
        if isinstance(as_of_date, str):
            as_of_date = datetime.fromisoformat(
                as_of_date.split(" ")[0].replace("/", "-")
            )

        as_of_str = as_of_date.strftime(DATE_FORMAT)
        window_start_str = (as_of_date - timedelta(days=window_days)).strftime(
            DATE_FORMAT
        )

        personal_best = self.db.execute(
            select(func.max(Reading.maximum)).where(
                Reading.user_id == user_id,
                Reading.maximum.isnot(None),
                Reading.date <= as_of_str,
                Reading.date >= window_start_str,
            )
        ).scalar_one_or_none()

        if personal_best is None:
            return None
        return thresholds_from_personal_best(personal_best)

    def _recalculate_zones_for_user_history(
        self, user_id: str, window_days: int = DEFAULT_ZONE_WINDOW_DAYS
    ) -> int:
        """Пересчитывает green_zone/yellow_zone для ВСЕЙ истории пользователя"""
        rows = self.db.execute(
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
            self.db.connection().execute(
                update(Reading)
                .where(Reading.id == bindparam("b_id"))
                .values(
                    green_zone=bindparam("green_zone"),
                    yellow_zone=bindparam("yellow_zone"),
                    red_zone=bindparam("red_zone"),
                ),
                updates,
            )
        return len(updates)

    def insert_reading(
        self,
        user_id: str,
        date,
        first_try: float,
        second_try: float,
        third_try: float,
    ) -> tuple:
        """Вставляет новую запись и сразу считает для неё зоны"""
        maximum = max(first_try, second_try, third_try)
        date_str = _to_date_str(date)

        thresholds = self.calculate_zone_thresholds(
            user_id, date, DEFAULT_ZONE_WINDOW_DAYS
        )
        if thresholds is None:
            thresholds = thresholds_from_personal_best(maximum)
        else:
            thresholds = thresholds_from_personal_best(
                max(thresholds.personal_best, maximum)
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
        self.db.add(reading)
        self.db.flush()

        zone = classify_zone(maximum, thresholds)
        return reading.id, thresholds, zone

    def find_reading(self, user_id: str, day, period: str) -> dict | None:
        """Показание пользователя за конкретный день+период (утро/вечер) —
        для добавления/исправления пропущенного значения задним числом
        (services/backfill_service.py). Если таких несколько (в норме не
        должно быть — обычно один замер на период в день), берётся самое
        позднее по времени."""
        day_start = f"{day.isoformat()} 00:00:00"
        day_end = f"{day.isoformat()} 23:59:59"
        rows = (
            self.db.execute(
                select(Reading)
                .where(
                    Reading.user_id == user_id,
                    Reading.date >= day_start,
                    Reading.date <= day_end,
                )
                .order_by(Reading.date.desc())
            )
            .scalars()
            .all()
        )
        for row in rows:
            if classify_period(row.date) == period:
                return {
                    "id": row.id,
                    "first_try": row.first_try,
                    "second_try": row.second_try,
                    "third_try": row.third_try,
                    "maximum": row.maximum,
                }
        return None

    def upsert_reading_for_period(
        self,
        user_id: str,
        day,
        period: str,
        first_try: float,
        second_try: float,
        third_try: float,
    ) -> dict:
        """Добавляет пропущенное показание или исправляет уже существующее за
        этот день+период. В отличие от insert_reading (используется при живой
        записи «сейчас», где новая запись всегда позже всех предыдущих),
        здесь дата может быть любой в прошлом — вставка/правка задним числом
        может изменить персональный рекорд для промежуточных дней, поэтому
        зоны пересчитываются по ВСЕЙ истории (как при импорте CSV), а не
        только вперёд по времени от одной записи."""
        existing = self.find_reading(user_id, day, period)
        maximum = max(first_try, second_try, third_try)

        if existing:
            row = self.db.get(Reading, existing["id"])
            row.first_try, row.second_try, row.third_try = (
                first_try,
                second_try,
                third_try,
            )
            row.maximum = maximum
            updated = True
        else:
            default_hour = 9 if period == "morning" else 20
            date_str = f"{day.isoformat()} {default_hour:02d}:00:00"
            row = Reading(
                user_id=user_id,
                date=date_str,
                first_try=first_try,
                second_try=second_try,
                third_try=third_try,
                maximum=maximum,
                green_zone=None,
                yellow_zone=None,
                red_zone=None,
            )
            self.db.add(row)
            updated = False

        self.db.flush()
        self._recalculate_zones_for_user_history(user_id)
        self.db.flush()
        self.db.refresh(row)

        thresholds = None
        if row.green_zone is not None:
            thresholds = ZoneThresholds(
                personal_best=maximum,
                green_zone=row.green_zone,
                yellow_zone=row.yellow_zone,
            )
        zone = classify_zone(maximum, thresholds)

        return {
            "updated": updated,
            "reading_id": row.id,
            "date": row.date,
            "maximum": maximum,
            "zone": zone,
            "green_zone": row.green_zone,
            "yellow_zone": row.yellow_zone,
        }

    def import_dataframe(self, df: pd.DataFrame, user_id: str) -> dict:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]

        required = {"First try", "Second try", "Third try", "Date"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"В файле не хватает колонок: {', '.join(sorted(missing))}"
            )

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

        readings_inserted = 0
        doses_inserted = 0
        extra_info_inserted = 0

        # Одна и та же сессия (self.db) для всех задействованных таблиц —
        # либо весь импорт целиком, либо (при ошибке и откате UnitOfWork)
        # ничего из него не попадёт в БД.
        users = UserRepository(self.db)
        medicines = MedicineRepository(self.db)
        extra_info = ExtraInfoRepository(self.db)

        users.ensure_user(user_id)
        for med_name in medicine_cols:
            medicines.get_or_create_medicine_id(user_id, med_name)

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
            self.db.add(
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
                medicine_id = medicines.get_or_create_medicine_id(user_id, med_name)
                medicines.add_taken_medicine(medicine_id, user_id, int(doses), date_str)
                doses_inserted += 1

            if "Extra info" in df.columns:
                flags = _parse_extra_info_cell(row.get("Extra info"))
                if any(flags.values()):
                    extra_info.add_extra_info(user_id, date_str, flags)
                    extra_info_inserted += 1

        # Пересчёт зон читает только что добавленные Reading через SELECT —
        # сессия сделана с autoflush=False, поэтому без явного flush() ORM их
        # не увидит (в старом коде эту роль играл промежуточный conn.commit()).
        self.db.flush()
        updated_zone_rows = self._recalculate_zones_for_user_history(user_id)

        return {
            "rows_in_file": len(df),
            "readings_inserted": readings_inserted,
            "doses_inserted": doses_inserted,
            "extra_info_inserted": extra_info_inserted,
            "zone_rows_recalculated": updated_zone_rows,
            "bad_dates_skipped": int(bad_dates),
        }

    def fetch_full_readings_df(
        self, user_id: str, start_str: str, end_str: str
    ) -> pd.DataFrame:
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
            self.db.execute(stmt).all(),
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
        self, user_id: str, start_str: str, end_str: str
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
        return pd.DataFrame(self.db.execute(stmt).all(), columns=["date", "maximum"])

    def fetch_history_since_df(self, user_id: str, since_str: str) -> pd.DataFrame:
        """Вся история с определённой даты, без верхней границы — для прогноза."""
        stmt = (
            select(Reading.date, Reading.maximum)
            .where(
                Reading.user_id == user_id,
                Reading.maximum.isnot(None),
                Reading.date >= since_str,
            )
            .order_by(Reading.date)
        )
        return pd.DataFrame(self.db.execute(stmt).all(), columns=["date", "maximum"])

    def fetch_all_readings_with_zones_df(self, user_id: str) -> pd.DataFrame:
        """Вся история показаний с уже посчитанными на тот момент зонами —
        для recommend_service.py."""
        stmt = (
            select(
                Reading.date, Reading.maximum, Reading.green_zone, Reading.yellow_zone
            )
            .where(
                Reading.user_id == user_id,
                Reading.maximum.isnot(None),
                Reading.green_zone.isnot(None),
            )
            .order_by(Reading.date)
        )
        return pd.DataFrame(
            self.db.execute(stmt).all(),
            columns=["date", "maximum", "green_zone", "yellow_zone"],
        )
