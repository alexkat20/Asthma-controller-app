"""Pydantic-схемы для HTTP-слоя (запросы/ответы эндпоинтов)."""

from pydantic import BaseModel


class ChatIn(BaseModel):
    user_id: str
    text: str


class ChatOut(BaseModel):
    reply: str
    quick_replies: list = []
    images: list = []


class UploadOut(BaseModel):
    reply: str


class NotificationsOut(BaseModel):
    messages: list = []
