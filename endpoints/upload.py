import io

import pandas as pd
from fastapi import APIRouter, File, Form, UploadFile

from repositories import database as db

router = APIRouter()


@router.post("/api/upload")
async def upload(user_id: str = Form(...), file: UploadFile = File(...)):
    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            data = pd.read_csv(io.BytesIO(content))
        elif file.filename.endswith((".xls", ".xlsx")):
            data = pd.read_excel(io.BytesIO(content))
        else:
            return {"reply": "Поддерживаются только файлы CSV и Excel."}

        conn = db.get_connection()
        db.ensure_user(conn, user_id)
        stats = db.import_dataframe(conn, data, user_id)
        conn.close()

        reply = (
            "✅ Данные загружены!\n"
            f"Строк в файле: {stats['rows_in_file']}\n"
            f"Добавлено показаний: {stats['readings_inserted']}\n"
            f"Записей о приёме препаратов: {stats['doses_inserted']}\n"
            f"Записей о состоянии: {stats['extra_info_inserted']}\n"
            f"Зоны пересчитаны для {stats['zone_rows_recalculated']} записей."
        )
        if stats["bad_dates_skipped"]:
            reply += f"\n⚠️ Пропущено строк с некорректной датой: {stats['bad_dates_skipped']}"
        return {"reply": reply}
    except Exception as exc:
        return {"reply": f"Ошибка при импорте: {exc}"}
