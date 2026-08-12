"""Pydantic-схемы для HTTP-слоя (запросы/ответы эндпоинтов)."""

from pydantic import BaseModel


class ChatIn(BaseModel):
    user_id: str
    text: str


class SliderSpec(BaseModel):
    min: int
    max: int
    default: int
    label: str
    unit: str = ""  # подпись рядом со значением, например "дн."


class ChatOut(BaseModel):
    reply: str
    quick_replies: list = []
    images: list = []
    download_url: str | None = None
    slider: SliderSpec | None = None
    table: dict | None = None


class UploadOut(BaseModel):
    reply: str


class NotificationsOut(BaseModel):
    messages: list = []
