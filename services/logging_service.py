"""Разбор и сохранение одного свободного сообщения с показаниями пикфлоу (NLP)."""

from datetime import datetime

from repositories import database as db
from services import nlp_service, recommend_service
from utils.formatting import FLAG_RU, ZONE_RU


def run_smart_log(user_id: str, text: str):
    """Возвращает готовый текст ответа, либо None, если в сообщении не нашлось показаний
    (значит, это не попытка записи, а что-то другое — вызывающий код покажет справку)."""
    conn = db.get_connection()
    db.ensure_user(conn, user_id)
    known_medicines = db.list_medicine_names(conn)
    parsed = nlp_service.parse_log_message(text, known_medicines)

    if not parsed["peak_flow"]:
        conn.close()
        return None

    values = parsed["peak_flow"][:3]
    while len(values) < 3:
        values.append(values[-1])

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M:%S")
    _, thresholds, zone = db.insert_reading(conn, user_id, now, *values)
    maximum = max(values)

    for med in parsed["medicines"]:
        medicine_id = db.get_or_create_medicine_id(conn, med["name"])
        db.add_taken_medicine(conn, medicine_id, user_id, med["dose"], date_str)

    flags = parsed["flags"]
    if any(flags.values()):
        db.add_extra_info(conn, user_id, date_str, flags)
    conn.commit()
    conn.close()

    zone_messages = {
        "green": f"✅ Пикфлоу {maximum:.0f} — {ZONE_RU['green']} зона (≥{thresholds.green_zone:.0f}). Стабильно.",
        "yellow": f"⚠️ Пикфлоу {maximum:.0f} — {ZONE_RU['yellow']} зона ({thresholds.yellow_zone:.0f}–{thresholds.green_zone:.0f}). Стоит понаблюдать за собой.",
        "red": f"🚨 Пикфлоу {maximum:.0f} — {ZONE_RU['red']} зона (<{thresholds.yellow_zone:.0f}). Рекомендуется консультация врача.",
    }
    med_str = (
        ", ".join(f"{m['name']} × {m['dose']}" for m in parsed["medicines"])
        or "не указано"
    )
    flags_str = ", ".join(FLAG_RU[f] for f, v in flags.items() if v) or "не указано"

    recommendation_block = ""
    if zone in ("yellow", "red"):
        conn2 = db.get_connection()
        rec = recommend_service.recommend_medicine(conn2, user_id)
        conn2.close()
        if rec:
            recommendation_block = "\n\n" + recommend_service.format_recommendation(rec)

    return (
        f"{zone_messages.get(zone, f'Сохранено: максимум {maximum:.0f}')}\n\n"
        f"Показания: {', '.join(str(int(v)) for v in values)}\n"
        f"Препараты: {med_str}\n"
        f"Состояние: {flags_str}"
        f"{recommendation_block}"
    )
