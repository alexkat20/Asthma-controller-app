from fastapi import APIRouter

from models.schemas import ChatIn, ChatOut
from services.chat_service import process_message

router = APIRouter()


@router.post("/api/chat", response_model=ChatOut)
def chat(payload: ChatIn) -> ChatOut:
    return process_message(payload.user_id, payload.text, payload.command)
