import re
from datetime import datetime

from models.schemas import ChatOut
from repositories.extra_info_repository import (
    EXTRA_INFO_FLAGS,
    SYMPTOM_FLAGS,
    TRIGGER_FLAGS,
)
from repositories.unit_of_work import UnitOfWork
from services import nlp_service, recommend_service, treatment_plan_service
from utils.dates import MORNING_CUTOFF_HOUR
from utils.numbers import extract_numbers
from utils.formatting import FLAG_RU, MAIN_MENU, ZONE_RU

NO_MEDICINE_LABEL = "Без препарата"
NO_TRIGGERS_LABEL = "Ничего из этого"
NO_SYMPTOMS_LABEL = "Ничего из этого"
ATTACKS_QUICK_REPLIES = ["0", "1", "2", "3"]

# «Менструальный цикл» как триггер имеет смысл предлагать кнопкой только
# женщинам — но текстом (свободный ввод) его всё равно можно указать любому.
_MENSTRUAL_FLAG = "menstrual_cycle"


def _extract_numbers(text: str) -> list:
    return extract_numbers(text)


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


def _trigger_quick_replies(user_id: str) -> list:
    with UnitOfWork() as uow:
        profile = uow.profiles.get_profile(user_id)
    is_female = bool(profile) and profile.get("gender") == "female"
    flags = (
        TRIGGER_FLAGS
        if is_female
        else [f for f in TRIGGER_FLAGS if f != _MENSTRUAL_FLAG]
    )
    return [FLAG_RU[f].capitalize() for f in flags] + [NO_TRIGGERS_LABEL]


def _symptom_quick_replies() -> list:
    return [FLAG_RU[f].capitalize() for f in SYMPTOM_FLAGS] + [NO_SYMPTOMS_LABEL]


def _prompt_triggers_step(session: dict, user_id: str) -> ChatOut:
    session["log_step"] = "triggers"
    return ChatOut(
        reply=(
            "Было ли сегодня что-то, что могло повлиять на состояние (триггеры)? "
            "Перечислите через запятую или выберите «Ничего из этого»."
        ),
        quick_replies=_trigger_quick_replies(user_id),
    )


def _prompt_symptoms_step(session: dict) -> ChatOut:
    session["log_step"] = "symptoms"
    return ChatOut(
        reply=(
            "Были ли сегодня симптомы? Перечислите через запятую или выберите «Ничего из этого»."
        ),
        quick_replies=_symptom_quick_replies(),
    )


def _merge_detected_flags(session: dict, text: str, no_label: str) -> None:
    tl = text.strip().lower()
    if no_label.lower() not in tl and "ничего" not in tl:
        new_flags = nlp_service.detect_state(text)
        existing = session.setdefault("log_data", {}).get("flags") or {}
        merged = {
            key: existing.get(key, False) or new_flags.get(key, False)
            for key in EXTRA_INFO_FLAGS
        }
        session["log_data"]["flags"] = merged


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

    with UnitOfWork() as uow:
        medicines = uow.medicines.list_medicines_with_doses(user_id)

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
    return _prompt_triggers_step(session, user_id)


def handle_triggers_step(user_id: str, session: dict, text: str) -> ChatOut:
    _merge_detected_flags(session, text, NO_TRIGGERS_LABEL)
    return _prompt_symptoms_step(session)


def handle_symptoms_step(user_id: str, session: dict, text: str) -> ChatOut:
    _merge_detected_flags(session, text, NO_SYMPTOMS_LABEL)
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

    medicine_name = data.get("medicine_name")
    doses = data.get("doses")
    flags = data.get("flags") or {}
    attacks_count = data.get("attacks_count")

    # Показания + (опционально) приём препарата + доп. состояние — одна
    # бизнес-операция на несколько таблиц, поэтому один UnitOfWork: либо
    # сохранится всё, либо (при ошибке) не сохранится ничего из этого.
    with UnitOfWork() as uow:
        uow.users.ensure_user(user_id)
        _, thresholds, zone = uow.readings.insert_reading(user_id, now, *values)

        if medicine_name and doses:
            medicine_id = uow.medicines.get_or_create_medicine_id(
                user_id, medicine_name
            )
            uow.medicines.add_taken_medicine(medicine_id, user_id, doses, date_str)

        if attacks_count is not None or any(flags.values()):
            uow.extra_info.add_extra_info(
                user_id, date_str, flags, attacks_count, record_time
            )

        uow.commit()
    maximum = max(values)

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
            rec = recommend_service.recommend_medicine(user_id)
            if rec:
                reply += "\n\n" + recommend_service.format_recommendation(rec)

    return ChatOut(reply=reply, quick_replies=MAIN_MENU)
