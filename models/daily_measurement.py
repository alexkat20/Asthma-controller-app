from sqlalchemy import Integer, String, Date
from sqlalchemy.orm import Mapped, mapped_column
from db.db_connection import Base
from datetime import date
from uuid6 import uuid7


class DailyMeasurementTable(Base):
    __tablename__ = 'daily_measurement'

    username: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(Date, nullable=False)
    first_measurement: Mapped[int] = mapped_column(Integer, nullable=False)
    second_measurement: Mapped[int] = mapped_column(Integer, nullable=False)
    third_measurement: Mapped[int] = mapped_column(Integer, nullable=False)

    max_measurement: Mapped[int] = mapped_column(Integer, nullable=False)
