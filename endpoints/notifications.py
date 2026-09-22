from fastapi import APIRouter

from services import notification_service

router = APIRouter()


@router.get("/api/notifications/{user_id}")
def get_notifications(user_id: str):
    return {"messages": notification_service.pop_all(user_id)}
