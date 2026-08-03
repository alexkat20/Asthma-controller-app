"""
Верхнеуровневый маршрутизатор сообщений чата.

Держит состояние диалога (в памяти процесса — session per user_id) и решает,
какому сервису передать управление: онбординг профиля, аналитика, умная запись
показаний, лекарства, напоминания, местоположение/аллергия.
"""

from models.schemas import ChatOut
from repositories.profile_repository import profile_exists
from services import (
    analytics_service,
    location_service,
    logging_service,
    medicine_service,
    profile_service,
    reminder_service,
)
from utils.dates import QUICK_PERIODS, parse_period
from utils.formatting import MAIN_MENU, help_text, welcome_text

SESSIONS: dict = {}

GREETINGS = {
    "начать",
    "старт",
    "/start",
    "привет",
    "меню",
    "хай",
    "hello",
    "hi",
    "start",
}
HELP_WORDS = {"помощь", "команды", "help", "?"}


def get_session(user_id: str) -> dict:
    return SESSIONS.setdefault(
        user_id,
        {"awaiting_period": None, "awaiting_medicine_name": False, "log_step": None},
    )


def process_message(user_id: str, text: str) -> ChatOut:
    session = get_session(user_id)
    t = text.strip()
    tl = t.lower()

    # Профиль — обязателен один раз, до чего-либо ещё.
    if session.get("onboarding_step"):
        return profile_service.continue_onboarding(user_id, session, t)

    if not profile_exists(user_id):
        return profile_service.start_onboarding(session)

    if tl in ("изменить профиль", "редактировать профиль", "обновить профиль"):
        return profile_service.start_onboarding(session)

    if "профиль" in tl:
        return ChatOut(
            reply=profile_service.show_profile(user_id), quick_replies=MAIN_MENU
        )

    if tl in GREETINGS:
        session["awaiting_period"] = None
        session["awaiting_medicine_name"] = False
        session["log_step"] = None
        session.pop("log_data", None)
        session.pop("medicine_options", None)
        return ChatOut(reply=welcome_text(), quick_replies=MAIN_MENU)

    if tl in HELP_WORDS:
        return ChatOut(reply=help_text(), quick_replies=MAIN_MENU)

    if session.get("awaiting_medicine_name"):
        session["awaiting_medicine_name"] = False
        return ChatOut(
            reply=medicine_service.add_medicine_from_text(t), quick_replies=MAIN_MENU
        )

    if session.get("awaiting_period"):
        days, custom = parse_period(t)
        if days is None and custom is None:
            return ChatOut(
                reply="Не понял период. Выберите один из вариантов ниже или пришлите диапазон ДД.ММ.ГГГГ-ДД.ММ.ГГГГ.",
                quick_replies=QUICK_PERIODS,
            )
        kind = session["awaiting_period"]
        session["awaiting_period"] = None
        if kind == "analysis":
            reply, images = analytics_service.run_analysis(user_id, days, custom)
        else:
            reply, images = analytics_service.run_plot(user_id, days, custom)
        return ChatOut(reply=reply, images=images, quick_replies=MAIN_MENU)

    # Мастер записи показаний (шаги: показания -> препарат -> количество доз)
    log_step = session.get("log_step")
    if log_step == "reading":
        return logging_service.handle_reading_input(user_id, session, t)
    if log_step == "medicine":
        return logging_service.handle_medicine_step(user_id, session, t)
    if log_step == "dose_count":
        return logging_service.handle_dose_count_step(user_id, session, t)

    if "анализ" in tl:
        session["awaiting_period"] = "analysis"
        return ChatOut(
            reply="За какой период построить анализ?", quick_replies=QUICK_PERIODS
        )

    if "график" in tl:
        session["awaiting_period"] = "plot"
        return ChatOut(
            reply="За какой период построить график?", quick_replies=QUICK_PERIODS
        )

    if "прогноз" in tl:
        reply, images = analytics_service.run_predict(user_id)
        return ChatOut(reply=reply, images=images, quick_replies=MAIN_MENU)

    if "напомин" in tl:
        return ChatOut(
            reply=reminder_service.handle_reminder_command(user_id, t),
            quick_replies=MAIN_MENU,
        )

    if tl.startswith("город "):
        return ChatOut(
            reply=location_service.set_user_location(
                user_id, t[len("город ") :].strip()
            ),
            quick_replies=MAIN_MENU,
        )

    if "аллерг" in tl or "пыльц" in tl:
        return ChatOut(
            reply=location_service.run_allergy_check(user_id), quick_replies=MAIN_MENU
        )

    if "записать показания" in tl or tl in (
        "запись",
        "показания",
        "новая запись",
        "записать",
    ):
        return logging_service.prompt_reading_entry(session)

    if "лекарств" in tl or "препарат" in tl:
        session["awaiting_medicine_name"] = True
        return ChatOut(
            reply="Введите название и дозу через точку с запятой, например: «Симбикорт; 2 дозы»."
        )

    # иначе, если сообщение похоже на показания (три и более числа) — начинаем запись
    if logging_service.looks_like_reading(t):
        return logging_service.handle_reading_input(user_id, session, t)

    return ChatOut(reply=help_text(), quick_replies=MAIN_MENU)
