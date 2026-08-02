"""Добавление/обновление препарата вручную (команда «добавить лекарство»)."""

from repositories import database as db


def add_medicine_from_text(text: str) -> str:
    if ";" in text:
        name, dose = (part.strip() for part in text.split(";", 1))
    else:
        name, dose = text.strip(), ""

    conn = db.get_connection()
    db.upsert_medicine(conn, name, dose)
    conn.close()
    return f"💊 Сохранено: {name} ({dose or 'доза не указана'})."
