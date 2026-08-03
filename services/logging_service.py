"""
Запись показаний пикфлоуметрии — пошаговый диалог (не одно свободное сообщение):

  1) пользователь сам вводит три показания (числа через пробел/запятую)
  2) препарат выбирается из предложенных кнопок (со стандартной дозой из БД)
  3) количество принятых доз/вдохов — целое число

Состояние текущего шага живёт в session (см. services/chat_service.py):
  session["log_step"]  — None | "reading" | "medicine" | "dose_count"
  session["log_data"]  — накопленные на текущий момент данные записи
  session["medicine_options"] — {текст_кнопки: имя_препарата_или_None} для шага 2

Состояние человека (спорт/стресс/аллергия/...) отдельным шагом не запрашивается —
чтобы не удлинять диалог, оно молча извлекается NLP-детектором из текста
показаний, если пользователь сам упомянул его в том же сообщении
(например: «450 460 470 занимался спортом»).
"""

import re
from datetime import datetime

from models.schemas import ChatOut
from repositories import database as db
from services import nlp_service, recommend_service
from utils.formatting import FLAG_RU, MAIN_MENU, ZONE_RU

NO_MEDICINE_LABEL = "Без препарата"


def _extract_numbers(text: str) -> list:
    return [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", text)]


def looks_like_reading(text: str) -> bool:
    """Похоже ли сообщение на попытку ввести показания (>=3 числа)?"""
    return len(_extract_numbers(text)) >= 3


def prompt_reading_entry(session: dict) -> ChatOut:
    """Явный старт мастера записи (например, по команде «записать показания»)."""
    session["log_step"] = "reading"
    session["log_data"] = {}
    return ChatOut(
        reply="Введите три показания пикфлоуметра через пробел, например: 450 460 470."
    )


def handle_reading_input(user_id: str, session: dict, text: str) -> ChatOut:
    """Шаг 1: разбор трёх показаний. Вызывается и по явному запросу, и когда
    пользователь просто прислал числа без команды."""
    numbers = _extract_numbers(text)
    if len(numbers) < 3:
        session["log_step"] = "reading"
        return ChatOut(
            reply="Не нашёл три числа. Введите три показания пикфлоуметра через пробел, например: 450 460 470."
        )

    values = numbers[:3]
    flags = nlp_service.detect_state(text)
    session["log_data"] = {"values": values, "flags": flags}

    conn = db.get_connection()
    medicines = db.list_medicines_with_doses(conn)
    conn.close()

    if not medicines:
        # В базе ещё нет ни одного препарата — сохраняем показания сразу, без шагов 2-3.
        session["log_step"] = None
        return _finalize(user_id, session)

    options = {NO_MEDICINE_LABEL: None}
    quick_replies = []
    for name, dose in medicines:
        label = f"{name} ({dose})" if dose else name
        options[label] = name
        quick_replies.append(label)
    quick_replies.append(NO_MEDICINE_LABEL)

    session["medicine_options"] = options
    session["log_step"] = "medicine"
    return ChatOut(reply="Какой препарат приняли?", quick_replies=quick_replies)


def handle_medicine_step(user_id: str, session: dict, text: str) -> ChatOut:
    """Шаг 2: выбор препарата из предложенных кнопок (или свой вариант текстом)."""
    options = session.get("medicine_options", {})
    key = text.strip()
    medicine_name = (
        options[key] if key in options else key
    )  # свой вариант -> создадим такой препарат

    if medicine_name is None:  # выбрали "Без препарата"
        session["log_step"] = None
        session.pop("medicine_options", None)
        return _finalize(user_id, session)

    session.setdefault("log_data", {})["medicine_name"] = medicine_name
    session["log_step"] = "dose_count"
    session.pop("medicine_options", None)
    return ChatOut(
        reply=f"Сколько доз/вдохов препарата «{medicine_name}» приняли?",
        quick_replies=["1", "2", "3"],
    )


def handle_dose_count_step(user_id: str, session: dict, text: str) -> ChatOut:
    """Шаг 3: количество принятых доз — целое число."""
    m = re.search(r"\d+", text)
    if not m:
        return ChatOut(
            reply="Введите целое число доз, например: 1, 2 или 3.",
            quick_replies=["1", "2", "3"],
        )
    session.setdefault("log_data", {})["doses"] = int(m.group(0))
    session["log_step"] = None
    return _finalize(user_id, session)


def _finalize(user_id: str, session: dict) -> ChatOut:
    data = session.pop("log_data", {})
    values = data.get("values")
    if not values:
        return ChatOut(
            reply="Что-то пошло не так — попробуйте записать показания заново.",
            quick_replies=MAIN_MENU,
        )

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M:%S")

    conn = db.get_connection()
    db.ensure_user(conn, user_id)
    _, thresholds, zone = db.insert_reading(conn, user_id, now, *values)
    maximum = max(values)

    medicine_name = data.get("medicine_name")
    doses = data.get("doses")
    if medicine_name and doses:
        medicine_id = db.get_or_create_medicine_id(conn, medicine_name)
        db.add_taken_medicine(conn, medicine_id, user_id, doses, date_str)

    flags = data.get("flags") or {}
    if any(flags.values()):
        db.add_extra_info(conn, user_id, date_str, flags)
    conn.commit()
    conn.close()

    zone_messages = {
        "green": f"✅ Пикфлоу {maximum:.0f} — {ZONE_RU['green']} зона (≥{thresholds.green_zone:.0f}). Стабильно.",
        "yellow": f"⚠️ Пикфлоу {maximum:.0f} — {ZONE_RU['yellow']} зона ({thresholds.yellow_zone:.0f}–{thresholds.green_zone:.0f}). Стоит понаблюдать за собой.",
        "red": f"🚨 Пикфлоу {maximum:.0f} — {ZONE_RU['red']} зона (<{thresholds.yellow_zone:.0f}). Рекомендуется консультация врача.",
    }
    med_str = f"{medicine_name} × {doses}" if medicine_name and doses else "не указано"
    flags_str = ", ".join(FLAG_RU[f] for f, v in flags.items() if v) or "не указано"

    recommendation_block = ""
    if zone in ("yellow", "red"):
        conn2 = db.get_connection()
        rec = recommend_service.recommend_medicine(conn2, user_id)
        conn2.close()
        if rec:
            recommendation_block = "\n\n" + recommend_service.format_recommendation(rec)

    return ChatOut(
        reply=(
            f"{zone_messages.get(zone, f'Сохранено: максимум {maximum:.0f}')}\n\n"
            f"Показания: {', '.join(str(int(v)) for v in values)}\n"
            f"Препарат: {med_str}\n"
            f"Состояние: {flags_str}"
            f"{recommendation_block}"
        ),
        quick_replies=MAIN_MENU,
    )
