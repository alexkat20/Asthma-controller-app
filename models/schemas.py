from pydantic import BaseModel, field_validator


class ChatIn(BaseModel):
    user_id: str
    text: str
    command: str | None = None


class QuickReply(BaseModel):
    label: str
    command: str | None = None


class SliderSpec(BaseModel):
    min: int
    max: int
    default: int
    label: str
    unit: str = ""


class ChatOut(BaseModel):
    reply: str
    quick_replies: list[QuickReply] = []
    images: list = []
    download_url: str | None = None
    slider: SliderSpec | None = None
    table: dict | None = None

    @field_validator("quick_replies", mode="before")
    @classmethod
    def _normalize_quick_replies(cls, value):
        if not value:
            return []
        return [
            {"label": item, "command": None} if isinstance(item, str) else item
            for item in value
        ]


class UploadOut(BaseModel):
    reply: str


class NotificationsOut(BaseModel):
    messages: list = []
