import re
from datetime import datetime

from models.schemas import ChatOut
from repositories import database as db
from services import nlp_service, recommend_service, treatment_plan_service
from utils.formatting import FLAG_RU, MAIN_MENU, ZONE_RU

MORNING_CUTOFF_HOUR = (
    12  # до этого часа — утренняя (только показания), после — вечерняя запись
)

NO_MEDICINE_LABEL = "Без препарата"
NO_STATE_LABEL = "Ничего из этого"
STATE_QUICK_REPLIES = [
    "Спорт",
    "Стресс",
    "Аллергия",
    "Болезнь",
    "Перелёт",
    NO_STATE_LABEL,
]
ATTACKS_QUICK_REPLIES = ["0", "1", "2", "3"]


def _extract_numbers(text: str) -> list:
    return [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", text)]


def looks_like_reading(text: str) -> bool:
    return len(_extract_numbers(text)) >= 3


def _is_evening(now: datetime) -> bool:
    return now.hour >= MORNING_CUTOFF_HOUR


def prompt_reading_entry(session: dict) -> ChatOut:
    session["log_step"] = "reading"
    session["log_data"] = {}
    return ChatOut(
        reply="Введите три показания пикфлоуметра через пробел, например: 450 460 470."
    )


def _prompt_attacks_step(session: dict) -> ChatOut:
    session["log_step"] = "attacks"
    return ChatOut(
        reply="Сколько приступов было сегодня?", quick_replies=ATTACKS_QUICK_REPLIES
    )


def _prompt_state_step(session: dict) -> ChatOut:
    session["log_step"] = "state"
    return ChatOut(
        reply=(
            "Было ли сегодня что-то из этого: спорт, стресс, аллергия, болезнь, перелёт? "
            "Перечислите через запятую или выберите «Ничего из этого»."
        ),
        quick_replies=STATE_QUICK_REPLIES,
    )


def handle_reading_input(user_id: str, session: dict, text: str) -> ChatOut:
    numbers = _extract_numbers(text)
    if len(numbers) < 3:
        session["log_step"] = "reading"
        return ChatOut(
            reply="Не нашёл три числа. Введите три показания пикфлоуметра через пробел, например: 450 460 470."
        )

    values = numbers[:3]
    now = datetime.now()

    if not _is_evening(now):
        # Утренняя запись — только показания, без препаратов/приступов/состояния.
        session["log_step"] = None
        return _finalize(user_id, {"values": values}, now)

    flags = nlp_service.detect_state(text)
    session["log_data"] = {"values": values, "flags": flags}

    conn = db.get_connection()
    medicines = db.list_medicines_with_doses(conn)
    conn.close()

    if not medicines:
        return _prompt_attacks_step(session)

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
    options = session.get("medicine_options", {})
    key = text.strip()
    medicine_name = options[key] if key in options else key
    session.pop("medicine_options", None)

    if medicine_name is None:  # выбрали "Без препарата"
        return _prompt_attacks_step(session)

    session.setdefault("log_data", {})["medicine_name"] = medicine_name
    session["log_step"] = "dose_count"
    return ChatOut(
        reply=f"Сколько доз/вдохов препарата «{medicine_name}» приняли?",
        quick_replies=["1", "2", "3"],
    )


def handle_dose_count_step(user_id: str, session: dict, text: str) -> ChatOut:
    m = re.search(r"\d+", text)
    if not m:
        return ChatOut(
            reply="Введите целое число доз, например: 1, 2 или 3.",
            quick_replies=["1", "2", "3"],
        )
    session.setdefault("log_data", {})["doses"] = int(m.group(0))
    return _prompt_attacks_step(session)


def handle_attacks_step(user_id: str, session: dict, text: str) -> ChatOut:
    m = re.search(r"\d+", text)
    if not m:
        return ChatOut(
            reply="Введите число приступов за сегодня (0, если не было).",
            quick_replies=ATTACKS_QUICK_REPLIES,
        )
    session.setdefault("log_data", {})["attacks_count"] = int(m.group(0))
    return _prompt_state_step(session)


def handle_state_step(user_id: str, session: dict, text: str) -> ChatOut:
    tl = text.strip().lower()
    if NO_STATE_LABEL.lower() not in tl and "ничего" not in tl:
        new_flags = nlp_service.detect_state(text)
        existing = session.setdefault("log_data", {}).get("flags") or {}
        merged = {
            key: existing.get(key, False) or new_flags.get(key, False)
            for key in FLAG_RU
        }
        session["log_data"]["flags"] = merged

    session["log_step"] = None
    data = session.pop("log_data", {})
    return _finalize(user_id, data, datetime.now())


def _finalize(user_id: str, data: dict, now: datetime) -> ChatOut:
    values = data.get("values")
    if not values:
        return ChatOut(
            reply="Что-то пошло не так — попробуйте записать показания заново.",
            quick_replies=MAIN_MENU,
        )

    date_str = now.strftime("%Y-%m-%d %H:%M:%S")
    record_time = now.strftime("%H:%M")

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
    attacks_count = data.get("attacks_count")
    if attacks_count is not None or any(flags.values()):
        db.add_extra_info(conn, user_id, date_str, flags, attacks_count, record_time)
    conn.commit()
    conn.close()

    zone_messages = {
        "green": f"✅ Пикфлоу {maximum:.0f} — {ZONE_RU['green']} зона (≥{thresholds.green_zone:.0f}). Стабильно.",
        "yellow": f"⚠️ Пикфлоу {maximum:.0f} — {ZONE_RU['yellow']} зона ({thresholds.yellow_zone:.0f}–{thresholds.green_zone:.0f}). Стоит понаблюдать за собой.",
        "red": f"🚨 Пикфлоу {maximum:.0f} — {ZONE_RU['red']} зона (<{thresholds.yellow_zone:.0f}). Рекомендуется консультация врача.",
    }
    reply = zone_messages.get(zone, f"Сохранено: максимум {maximum:.0f}")
    reply += f"\n\nПоказания: {', '.join(str(int(v)) for v in values)}"

    if attacks_count is not None:
        med_str = (
            f"{medicine_name} × {doses}" if medicine_name and doses else "не указано"
        )
        flags_str = ", ".join(FLAG_RU[f] for f, v in flags.items() if v) or "не указано"
        reply += (
            f"\nПрепарат: {med_str}\n"
            f"Приступов за день: {attacks_count}\n"
            f"Состояние: {flags_str}"
        )

        plan_guidance = treatment_plan_service.get_guidance_for_zone(user_id, zone)
        if plan_guidance:
            label = "ухудшении" if zone == "yellow" else "приступе"
            reply += f"\n\n📋 План врача при {label}: {plan_guidance}"

        if attacks_count and attacks_count > 0:
            attack_plan = treatment_plan_service.get_attack_guidance(user_id)
            if attack_plan and zone != "red":
                reply += f"\n\n📋 План врача на случай приступа: {attack_plan}"

        if zone in ("yellow", "red") and not plan_guidance:
            conn2 = db.get_connection()
            rec = recommend_service.recommend_medicine(conn2, user_id)
            conn2.close()
            if rec:
                reply += "\n\n" + recommend_service.format_recommendation(rec)

    return ChatOut(reply=reply, quick_replies=MAIN_MENU)
