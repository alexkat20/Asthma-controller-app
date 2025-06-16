from typing import Optional, List
from sqlalchemy.exc import SQLAlchemyError
from db.db_connection import connection
from models.daily_measurement import DailyMeasurementTable
from datetime import date


@connection
async def save_daily_measurements(session,
                                  username: str,
                                  measurements: List[int]) -> Optional[DailyMeasurementTable]:

    new_measurement = DailyMeasurementTable(
        username=username,
        date=date.today(),
        first_measurement=measurements[0],
        second_measurement=measurements[1],
        third_measurement=measurements[2],
        max_measurement=max(measurements),
    )
    session.add(new_measurement)
    await session.commit()
    return new_measurement
