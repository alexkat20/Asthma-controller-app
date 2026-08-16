"""
Peak Flow — веб-чат-бот (без Telegram).

Структура проекта:
    models/       — Pydantic-схемы и доменные структуры данных
    repositories/ — весь SQL и работа с БД, больше никто напрямую в БД не ходит
    services/     — бизнес-логика (NLP, прогноз, рекомендации, аллергия, чат-роутинг)
    endpoints/    — HTTP-роутеры FastAPI, тонкие — только вызывают services
    utils/        — общие мелочи без побочных эффектов (даты, форматирование, графики)
    static/       — фронтенд (чат-интерфейс: HTML/CSS/JS, без фреймворков)

Запуск веб-приложения: uvicorn main:app --reload --port 8000
Открыть: http://localhost:8000

Фоновый планировщик (напоминания, ежемесячный ACT) запускается ОТДЕЛЬНО:
    python scheduler_worker.py
Он больше не часть этого процесса намеренно: если веб-приложение развёрнуто
с несколькими воркерами/инстансами (uvicorn --workers N, несколько подов и
т.п.), планировщик внутри каждого из них дублировал бы напоминания N раз.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from endpoints import chat, notifications, report, upload, export
from repositories.database import init_db

SERVER_HOST = "localhost"
SERVER_PORT = 8000

app = FastAPI(title="Peak Flow Chat Bot")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

init_db()

app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(notifications.router)
app.include_router(report.router)
app.include_router(export.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
