from typing import Optional, List
from sqlalchemy.exc import SQLAlchemyError
from db.db_connection import connection
from models.taken_medicine import TakenMedicineTable
from datetime import date


@connection
async def save_medicine(session, medicine: str) -> Optional[TakenMedicineTable]:
    new_medicine = TakenMedicineTable(
        date=date.today(),
        medicine=medicine
    )
    session.add(new_medicine)
    await session.commit()
    return new_medicine