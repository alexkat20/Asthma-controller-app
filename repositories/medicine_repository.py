import pandas as pd
from sqlalchemy import select

from repositories.base_repository import BaseRepository
from repositories.orm_models import Medicine, TakenMedicine
from repositories.user_repository import UserRepository


class MedicineRepository(BaseRepository):
    def _find_user_medicine(self, user_id: str, medicine_name: str):
        """Ищет препарат пользователя без учёта регистра"""
        target = medicine_name.strip().lower()
        rows = self.db.execute(
            select(Medicine).where(Medicine.user_id == user_id)
        ).scalars()
        for med in rows:
            if med.medicine_name.strip().lower() == target:
                return med
        return None

    def get_or_create_medicine_id(
        self, user_id: str, medicine_name: str, dose: str = ""
    ) -> int:
        existing = self._find_user_medicine(user_id, medicine_name)
        if existing:
            return existing.medicine_id

        medicine = Medicine(user_id=user_id, medicine_name=medicine_name, dose=dose)
        self.db.add(medicine)
        self.db.flush()  # получить medicine_id, не завершая внешнюю транзакцию
        return medicine.medicine_id

    def add_taken_medicine(
        self, medicine_id: int, user_id: str, doses: int, date_str: str
    ) -> None:
        self.db.add(
            TakenMedicine(
                medicine_id=medicine_id, user_id=user_id, doses=doses, date=date_str
            )
        )

    def add_medicine(self, user_id: str, medicine_name: str, dose: str = "") -> str:
        """Добавляет препарат в личный список пользователя"""
        UserRepository(self.db).ensure_user(user_id)
        existing = self._find_user_medicine(user_id, medicine_name)
        if existing:
            if dose and dose != (existing.dose or ""):
                existing.dose = dose
                return "dose_updated"
            return "exists"

        self.db.add(Medicine(user_id=user_id, medicine_name=medicine_name, dose=dose))
        return "created"

    def list_medicine_names(self, user_id: str) -> list:
        return list(
            self.db.execute(
                select(Medicine.medicine_name).where(Medicine.user_id == user_id)
            )
            .scalars()
            .all()
        )

    def list_medicines_with_doses(self, user_id: str) -> list:
        """Возвращает [(medicine_name, dose), ...] только для этого пользователя."""
        rows = self.db.execute(
            select(Medicine.medicine_name, Medicine.dose)
            .where(Medicine.user_id == user_id)
            .order_by(Medicine.medicine_name)
        ).all()
        return [(r.medicine_name, r.dose) for r in rows]

    def fetch_medicine_doses_df(
        self, user_id: str, start_str: str, end_str: str
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
            self.db.execute(stmt).all(), columns=["date", "medicine_name", "doses"]
        )

    def fetch_all_taken_medicine_with_names_df(self, user_id: str) -> pd.DataFrame:
        stmt = (
            select(TakenMedicine.date, Medicine.medicine_name)
            .join(Medicine, Medicine.medicine_id == TakenMedicine.medicine_id)
            .where(TakenMedicine.user_id == user_id)
        )
        return pd.DataFrame(
            self.db.execute(stmt).all(), columns=["date", "medicine_name"]
        )
