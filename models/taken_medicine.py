from sqlalchemy import ForeignKey, String, Date
from sqlalchemy.orm import Mapped, mapped_column
from db.db_connection import Base
from datetime import date
from uuid6 import uuid7


class TakenMedicineTable(Base):
    __tablename__ = 'taken_medicine'

    date: Mapped[str] = mapped_column(Date, nullable=False)
    daily_measurement_id: Mapped[str] = mapped_column(String, nullable=False)

    medicine: Mapped[str] = mapped_column(ForeignKey('medicine.id'), nullable=False)
