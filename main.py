"""
Peak Flow — веб-чат-бот (без Telegram).

Структура проекта:
    models/       — Pydantic-схемы и доменные структуры данных
    repositories/ — весь SQL и работа с БД, больше никто напрямую в БД не ходит
    services/     — бизнес-логика (NLP, прогноз, рекомендации, аллергия, чат-роутинг)
    endpoints/    — HTTP-роутеры FastAPI, тонкие — только вызывают services
    utils/        — общие мелочи без побочных эффектов (даты, форматирование, графики)
    static/       — фронтенд (чат-интерфейс: HTML/CSS/JS, без фреймворков)

Запуск: uvicorn main:app --reload --port 8000
Открыть: http://localhost:8000
"""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from endpoints import chat, notifications, upload
from repositories.database import init_db
from services.reminder_service import start_scheduler

app = FastAPI(title="Peak Flow Chat Bot")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

init_db()

app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(notifications.router)

SERVER_HOST = "localhost"
SERVER_PORT = 8080


@app.on_event("startup")
def _start_scheduler() -> None:
    start_scheduler()


# ---------------------------------------------------------------------------
# Статика (фронтенд). Путь абсолютный — не зависит от того, из какой папки
# запущен uvicorn (частая причина "Not Found" при разворачивании на сервере).
# ---------------------------------------------------------------------------
STATIC_DIR = Path(__file__).resolve().parent / "static"
_required_static_files = ["index.html", "style.css", "script.js"]
_missing = [f for f in _required_static_files if not (STATIC_DIR / f).is_file()]
if not STATIC_DIR.is_dir() or _missing:
    print(
        f"[main.py] Не найдена папка static с нужными файлами рядом с main.py: {STATIC_DIR}\n"
        f"[main.py] Отсутствуют файлы: {_missing or 'вся папка static'}\n"
        "[main.py] Скопируйте index.html, style.css и script.js в static/ рядом с main.py "
        "(в той же папке, где лежит main.py, а не в папке, откуда вы запускаете uvicorn).",
        file=sys.stderr,
    )
else:
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
