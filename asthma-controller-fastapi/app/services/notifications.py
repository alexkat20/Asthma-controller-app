from datetime import time
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session
from app.models import crud
from app.utils import send_notification_message


async def send_daily_notification(user_id: int, db: Session):
    user_data = crud.get_user_data(user_id, db)
    if user_data:
        avg_peak_flow = crud.calculate_average_peak_flow(user_id, db)
        yesterday_peak_flow = crud.get_yesterday_peak_flow(user_id, db)
        trend = crud.get_trend(user_id, db)

        message = (
            f"📊 Daily Report:\n"
            f"Expected peak flow today: {avg_peak_flow:.1f}\n"
            f"Yesterday's value: {yesterday_peak_flow:.1f}\n"
            f"Trend: Today is expected to be {trend} compared to yesterday."
        )
        await send_notification_message(user_id, message)


def schedule_daily_notifications(
    user_id: int, db: Session, background_tasks: BackgroundTasks
):
    background_tasks.add_task(send_daily_notification, user_id, db)
