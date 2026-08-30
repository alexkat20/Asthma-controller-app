from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from endpoints import chat, notifications, report, upload, export
from repositories.db_engine import init_db

SERVER_HOST = "0.0.0.0"
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
