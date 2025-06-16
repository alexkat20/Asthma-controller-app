from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from db.db_connection import Base


class MedicineTable(Base):
    __tablename__ = 'medicine'

    medicine_name: Mapped[str] = mapped_column(String, nullable=False)
    dose: Mapped[str] = mapped_column(String, nullable=False)
