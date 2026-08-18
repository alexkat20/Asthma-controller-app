import re
from datetime import datetime

from models.schemas import ChatOut
from repositories import database as db
from repositories import session_repository
from repositories.profile_repository import profile_exists
from services import (
    act_service,
    analytics_service,
    export_service,
    family_service,
    location_service,
    logging_service,
    medicine_service,
    profile_service,
    reminder_service,
    table_service,
    treatment_plan_service,
)
from utils.dates import QUICK_PERIODS, parse_period
from utils.formatting import (
    MAIN_MENU,
    READ_ONLY_MENU,
    help_text,
    read_only_notice,
    read_only_welcome,
    welcome_text,
)

_DEFAULT_SESSION = {
    "awaiting_period": None,
    "awaiting_medicine_name": False,
    "awaiting_table_days": False,
    "log_step": None,
    "act_step": None,
    "plan_step": None,
}

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


def _export_download_url(user_id: str, days, custom_range) -> str:
    if custom_range:
        start, end = custom_range
        return f"/api/export/{user_id}?start={start:%Y-%m-%d}&end={end:%Y-%m-%d}"
    return f"/api/export/{user_id}?days={days}"


def get_session(user_id: str) -> dict:
    """Загружает состояние диалога из БД"""
    conn = db.get_connection()
    try:
        stored = session_repository.load_session(conn, user_id)
    finally:
        conn.close()
    session = dict(_DEFAULT_SESSION)
    session.update(stored)
    return session


def _persist_session(user_id: str, session: dict) -> None:
    conn = db.get_connection()
    try:
        session_repository.save_session(
            conn, user_id, session, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    finally:
        conn.close()


def _table_days_prompt() -> ChatOut:
    return ChatOut(
        reply="За сколько последних дней показать таблицу?",
        slider={
            "min": table_service.MIN_DAYS,
            "max": table_service.MAX_DAYS,
            "default": table_service.DEFAULT_DAYS,
            "label": "Дней",
            "unit": "дн.",
        },
    )


def process_message(user_id: str, text: str) -> ChatOut:
    session = get_session(user_id)
    t = text.strip()
    tl = t.lower()

    effective_user_id, read_only = family_service.resolve_viewer(user_id)
    if read_only:
        result = _process_read_only(effective_user_id, session, t, tl)
    else:
        result = _process_full(effective_user_id, session, t, tl)

    _persist_session(user_id, session)
    return result


def _process_read_only(user_id: str, session: dict, t: str, tl: str) -> ChatOut:
    if tl in GREETINGS or tl in HELP_WORDS:
        session["awaiting_period"] = None
        return ChatOut(reply=read_only_welcome(), quick_replies=READ_ONLY_MENU)

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
        elif kind == "plot":
            reply, images = analytics_service.run_plot(user_id, days, custom)
        else:
            return ChatOut(
                reply="📄 Экспорт готов — файл начнёт скачиваться автоматически.",
                quick_replies=READ_ONLY_MENU,
                download_url=_export_download_url(user_id, days, custom),
            )
        return ChatOut(reply=reply, images=images, quick_replies=READ_ONLY_MENU)

    if session.get("awaiting_table_days"):
        session["awaiting_table_days"] = False
        m = re.search(r"\d+", t)
        days = int(m.group(0)) if m else table_service.DEFAULT_DAYS
        caption, table = table_service.build_table_data(user_id, days)
        return ChatOut(reply=caption, table=table, quick_replies=READ_ONLY_MENU)

    if "таблиц" in tl:
        session["awaiting_table_days"] = True
        return _table_days_prompt()

    if "экспорт" in tl or "скачать данные" in tl or "выгрузить" in tl:
        session["awaiting_period"] = "export"
        return ChatOut(
            reply="За какой период выгрузить данные?", quick_replies=QUICK_PERIODS
        )

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
        return ChatOut(reply=reply, images=images, quick_replies=READ_ONLY_MENU)

    if "аллерг" in tl or "пыльц" in tl:
        return ChatOut(
            reply=location_service.run_allergy_check(user_id),
            quick_replies=READ_ONLY_MENU,
        )

    if "план лечения" in tl or "назначения врача" in tl or "план врача" in tl:
        return ChatOut(
            reply=treatment_plan_service.show_plan(user_id),
            quick_replies=READ_ONLY_MENU,
        )

    if "тест" in tl or "act" in tl:
        return ChatOut(
            reply=act_service.show_act_status(user_id), quick_replies=READ_ONLY_MENU
        )

    if "отчёт" in tl or "отчет" in tl:
        return ChatOut(
            reply="📄 Отчёт готов — откроется в новой вкладке.",
            quick_replies=READ_ONLY_MENU,
            download_url=f"/api/report/{user_id}",
        )

    if "профиль" in tl:
        return ChatOut(
            reply=profile_service.show_profile(user_id), quick_replies=READ_ONLY_MENU
        )

    return ChatOut(reply=read_only_notice(), quick_replies=READ_ONLY_MENU)


def _process_full(user_id: str, session: dict, t: str, tl: str) -> ChatOut:
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
        session["act_step"] = None
        session.pop("log_data", None)
        session.pop("medicine_options", None)
        session.pop("act_answers", None)
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
        elif kind == "plot":
            reply, images = analytics_service.run_plot(user_id, days, custom)
        else:
            return ChatOut(
                reply="📄 Экспорт готов — файл начнёт скачиваться автоматически.",
                quick_replies=MAIN_MENU,
                download_url=_export_download_url(user_id, days, custom),
            )
        return ChatOut(reply=reply, images=images, quick_replies=MAIN_MENU)

    log_step = session.get("log_step")
    if log_step == "reading":
        return logging_service.handle_reading_input(user_id, session, t)
    if log_step == "medicine":
        return logging_service.handle_medicine_step(session, t)
    if log_step == "dose_count":
        return logging_service.handle_dose_count_step(session, t)
    if log_step == "attacks":
        return logging_service.handle_attacks_step(session, t)
    if log_step == "state":
        return logging_service.handle_state_step(user_id, session, t)

    if session.get("plan_step") is not None:
        return treatment_plan_service.continue_plan_edit(user_id, session, t)

    if "изменить план" in tl or "обновить план" in tl or "заполнить план" in tl:
        return treatment_plan_service.start_plan_edit(session)

    if "план лечения" in tl or "назначения врача" in tl or "план врача" in tl:
        return ChatOut(
            reply=treatment_plan_service.show_plan(user_id),
            quick_replies=["✏️ Изменить план"] + MAIN_MENU,
        )

    if session.get("act_step") is not None:
        return act_service.continue_act(user_id, session, t)

    if session.get("awaiting_table_days"):
        session["awaiting_table_days"] = False
        m = re.search(r"\d+", t)
        days = int(m.group(0)) if m else table_service.DEFAULT_DAYS
        caption, table = table_service.build_table_data(user_id, days)
        return ChatOut(reply=caption, table=table, quick_replies=MAIN_MENU)

    if "таблиц" in tl:
        session["awaiting_table_days"] = True
        return _table_days_prompt()

    if "экспорт" in tl or "скачать данные" in tl or "выгрузить" in tl:
        session["awaiting_period"] = "export"
        return ChatOut(
            reply="За какой период выгрузить данные?", quick_replies=QUICK_PERIODS
        )

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

    if "статус теста" in tl or "результат теста" in tl:
        return ChatOut(
            reply=act_service.show_act_status(user_id), quick_replies=MAIN_MENU
        )

    if "тест контроля" in tl or "act" in tl or "тест астмы" in tl:
        return act_service.start_act(session)

    if "отчёт" in tl or "отчет" in tl:
        return ChatOut(
            reply="📄 Отчёт для визита к врачу готов — откроется в новой вкладке, оттуда можно распечатать или сохранить как PDF.",
            quick_replies=MAIN_MENU,
            download_url=f"/api/report/{user_id}",
        )

    if "отозвать доступ" in tl:
        token = t[tl.index("отозвать доступ") + len("отозвать доступ") :].strip()
        return ChatOut(
            reply=family_service.revoke(user_id, token), quick_replies=MAIN_MENU
        )

    if "мои доступы" in tl or "ссылки доступа" in tl:
        return ChatOut(
            reply=family_service.list_shares_text(user_id), quick_replies=MAIN_MENU
        )

    if "семейный доступ" in tl:
        label = t[tl.index("семейный доступ") + len("семейный доступ") :].strip()
        token = family_service.generate_share_link(user_id, label)
        who = f" для «{label}»" if label else ""
        return ChatOut(
            reply=(
                f"👪 Ссылка только для чтения создана{who}.\n\n"
                f"Код доступа: {token}\n\n"
                "Передайте его тому, кому открываете доступ — на его устройстве нужно открыть "
                f"адрес вашего приложения с параметром: ?view={token}\n"
                "Например: https://ваш-сервер/?view=" + token + "\n\n"
                f"Список активных ссылок — «мои доступы». Отозвать — «отозвать доступ {token}»."
            ),
            quick_replies=MAIN_MENU,
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

    if logging_service.looks_like_reading(t):
        return logging_service.handle_reading_input(user_id, session, t)

    return ChatOut(reply=help_text(), quick_replies=MAIN_MENU)
