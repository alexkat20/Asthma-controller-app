import re
from datetime import datetime

from models.schemas import ChatOut, QuickReply
from repositories import database as db
from repositories import session_repository
from repositories.profile_repository import profile_exists
from services import (
    act_service,
    analytics_service,
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
    "awaiting_city": False,
    "awaiting_reminder_time": False,
    "awaiting_family_label": False,
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


def _reset_wizards(session: dict) -> None:
    session["awaiting_period"] = None
    session["awaiting_medicine_name"] = False
    session["awaiting_table_days"] = False
    session["awaiting_city"] = False
    session["awaiting_reminder_time"] = False
    session["awaiting_family_label"] = False
    session["log_step"] = None
    session["act_step"] = None
    session["plan_step"] = None
    session.pop("log_data", None)
    session.pop("medicine_options", None)
    session.pop("act_answers", None)
    session.pop("plan_data", None)


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


def process_message(user_id: str, text: str, command: str | None = None) -> ChatOut:
    session = get_session(user_id)
    t = text.strip()
    tl = t.lower()

    effective_user_id, read_only = family_service.resolve_viewer(user_id)
    if read_only:
        result = _process_read_only(effective_user_id, session, t, tl, command)
    else:
        result = _process_full(effective_user_id, session, t, tl, command)

    _persist_session(user_id, session)
    return result


def _process_full(
    user_id: str, session: dict, t: str, tl: str, command: str | None
) -> ChatOut:
    if session.get("onboarding_step"):
        return profile_service.continue_onboarding(user_id, session, t)
    if not profile_exists(user_id):
        return profile_service.start_onboarding(session)

    if tl in GREETINGS:
        _reset_wizards(session)
        return ChatOut(reply=welcome_text(), quick_replies=MAIN_MENU)
    if tl in HELP_WORDS:
        return ChatOut(reply=help_text(), quick_replies=MAIN_MENU)

    log_step = session.get("log_step")
    if log_step == "reading":
        return logging_service.handle_reading_input(user_id, session, t)
    if log_step == "medicine":
        return logging_service.handle_medicine_step(user_id, session, t)
    if log_step == "dose_count":
        return logging_service.handle_dose_count_step(user_id, session, t)
    if log_step == "attacks":
        return logging_service.handle_attacks_step(user_id, session, t)
    if log_step == "state":
        return logging_service.handle_state_step(user_id, session, t)

    if session.get("plan_step") is not None:
        return treatment_plan_service.continue_plan_edit(user_id, session, t)

    if session.get("act_step") is not None:
        return act_service.continue_act(user_id, session, t)

    if command:
        cmd_id = command.split(":", 1)[0]
        handler = _FULL_COMMANDS.get(cmd_id)
        if handler:
            _reset_wizards(session)
            return handler(user_id, session, command)

    if session.get("awaiting_medicine_name"):
        session["awaiting_medicine_name"] = False
        return ChatOut(
            reply=medicine_service.add_medicine_from_text(t), quick_replies=MAIN_MENU
        )

    if session.get("awaiting_city"):
        session["awaiting_city"] = False
        reply = location_service.set_user_location(user_id, t)
        if location_service.get_user_location(user_id) is not None:
            reply += "\n\n" + location_service.run_allergy_check(user_id)
        return ChatOut(reply=reply, quick_replies=MAIN_MENU)

    if session.get("awaiting_reminder_time"):
        session["awaiting_reminder_time"] = False
        return ChatOut(
            reply=reminder_service.handle_reminder_command(user_id, t),
            quick_replies=MAIN_MENU,
        )

    if session.get("awaiting_family_label"):
        session["awaiting_family_label"] = False
        label = "" if tl in ("без названия", "пропустить") else t
        return _create_family_share(user_id, label)

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

    if session.get("awaiting_table_days"):
        session["awaiting_table_days"] = False
        m = re.search(r"\d+", t)
        days = int(m.group(0)) if m else table_service.DEFAULT_DAYS
        caption, table = table_service.build_table_data(user_id, days)
        return ChatOut(reply=caption, table=table, quick_replies=MAIN_MENU)

    # 6) Похоже на показания (три и более числа) — числовой паттерн, не ключевые слова.
    if logging_service.looks_like_reading(t):
        return logging_service.handle_reading_input(user_id, session, t)

    # 7) Ничего не подошло — показываем меню, ничего не угадывая по словам.
    return ChatOut(reply=help_text(), quick_replies=MAIN_MENU)


def _create_family_share(user_id: str, label: str) -> ChatOut:
    token = family_service.generate_share_link(user_id, label)
    who = f" для «{label}»" if label else ""
    return ChatOut(
        reply=(
            f"👪 Ссылка только для чтения создана{who}.\n\n"
            f"Код доступа: {token}\n\n"
            "Передайте его тому, кому открываете доступ — на его устройстве нужно открыть "
            f"адрес вашего приложения с параметром: ?view={token}\n"
            "Например: https://ваш-сервер/?view=" + token
        ),
        quick_replies=MAIN_MENU,
    )


def _cmd_log_reading(user_id: str, session: dict, command: str) -> ChatOut:
    return logging_service.prompt_reading_entry(session)


def _cmd_analysis(user_id: str, session: dict, command: str) -> ChatOut:
    session["awaiting_period"] = "analysis"
    return ChatOut(
        reply="За какой период построить анализ?", quick_replies=QUICK_PERIODS
    )


def _cmd_plot(user_id: str, session: dict, command: str) -> ChatOut:
    session["awaiting_period"] = "plot"
    return ChatOut(
        reply="За какой период построить график?", quick_replies=QUICK_PERIODS
    )


def _cmd_table(user_id: str, session: dict, command: str) -> ChatOut:
    session["awaiting_table_days"] = True
    return _table_days_prompt()


def _cmd_predict(user_id: str, session: dict, command: str) -> ChatOut:
    reply, images = analytics_service.run_predict(user_id)
    return ChatOut(reply=reply, images=images, quick_replies=MAIN_MENU)


def _cmd_allergy(user_id: str, session: dict, command: str) -> ChatOut:
    if location_service.get_user_location(user_id) is None:
        session["awaiting_city"] = True
        return ChatOut(reply="Сначала укажите город — напишите его название.")
    reply = location_service.run_allergy_check(user_id)
    return ChatOut(
        reply=reply,
        quick_replies=[QuickReply(label="🏙 Изменить город", command="city_change")]
        + MAIN_MENU,
    )


def _cmd_city_change(user_id: str, session: dict, command: str) -> ChatOut:
    session["awaiting_city"] = True
    return ChatOut(reply="Напишите название нового города.")


def _cmd_add_medicine(user_id: str, session: dict, command: str) -> ChatOut:
    session["awaiting_medicine_name"] = True
    return ChatOut(
        reply="Введите название и дозу через точку с запятой, например: «Симбикорт; 2 дозы»."
    )


def _cmd_reminder(user_id: str, session: dict, command: str) -> ChatOut:
    status = reminder_service.handle_reminder_command(user_id, "")
    session["awaiting_reminder_time"] = True
    return ChatOut(
        reply=status + "\n\nЧтобы задать/изменить время — напишите его в формате ЧЧ:ММ."
    )


def _cmd_act_test(user_id: str, session: dict, command: str) -> ChatOut:
    return act_service.start_act(session)


def _cmd_plan_view(user_id: str, session: dict, command: str) -> ChatOut:
    return ChatOut(
        reply=treatment_plan_service.show_plan(user_id),
        quick_replies=[QuickReply(label="✏️ Изменить план", command="plan_edit")]
        + MAIN_MENU,
    )


def _cmd_plan_edit(user_id: str, session: dict, command: str) -> ChatOut:
    return treatment_plan_service.start_plan_edit(session)


def _cmd_report(user_id: str, session: dict, command: str) -> ChatOut:
    return ChatOut(
        reply="📄 Отчёт для визита к врачу готов — откроется в новой вкладке, оттуда можно распечатать или сохранить как PDF.",
        quick_replies=MAIN_MENU,
        download_url=f"/api/report/{user_id}",
    )


def _cmd_export(user_id: str, session: dict, command: str) -> ChatOut:
    session["awaiting_period"] = "export"
    return ChatOut(
        reply="За какой период выгрузить данные?", quick_replies=QUICK_PERIODS
    )


def _cmd_family_share(user_id: str, session: dict, command: str) -> ChatOut:
    shares = family_service.list_shares(user_id)
    reply = ""
    buttons = []
    if shares:
        reply = (
            "Активные ссылки:\n"
            + "\n".join(f"«{s['label']}» — код: {s['token']}" for s in shares)
            + "\n\n"
        )
        buttons = [
            QuickReply(
                label=f"🗑 Отозвать «{s['label']}»",
                command=f"family_revoke:{s['token']}",
            )
            for s in shares
        ]
    reply += "Введите название для новой ссылки (или нажмите «Без названия»)."
    session["awaiting_family_label"] = True
    return ChatOut(reply=reply, quick_replies=buttons + ["Без названия"])


def _cmd_family_revoke(user_id: str, session: dict, command: str) -> ChatOut:
    token = command.split(":", 1)[1]
    return ChatOut(reply=family_service.revoke(user_id, token), quick_replies=MAIN_MENU)


def _cmd_profile_view(user_id: str, session: dict, command: str) -> ChatOut:
    return ChatOut(
        reply=profile_service.show_profile(user_id),
        quick_replies=[QuickReply(label="✏️ Изменить профиль", command="profile_edit")]
        + MAIN_MENU,
    )


def _cmd_profile_edit(user_id: str, session: dict, command: str) -> ChatOut:
    return profile_service.start_onboarding(session)


_FULL_COMMANDS = {
    "log_reading": _cmd_log_reading,
    "analysis": _cmd_analysis,
    "plot": _cmd_plot,
    "table": _cmd_table,
    "predict": _cmd_predict,
    "allergy": _cmd_allergy,
    "city_change": _cmd_city_change,
    "add_medicine": _cmd_add_medicine,
    "reminder": _cmd_reminder,
    "act_test": _cmd_act_test,
    "plan_view": _cmd_plan_view,
    "plan_edit": _cmd_plan_edit,
    "report": _cmd_report,
    "export": _cmd_export,
    "family_share": _cmd_family_share,
    "family_revoke": _cmd_family_revoke,
    "profile_view": _cmd_profile_view,
    "profile_edit": _cmd_profile_edit,
}


# ---------------------------------------------------------------------------
# Read-only (семейный доступ) — подмножество команд, ничего не пишущего.
# ---------------------------------------------------------------------------


def _ro_analysis(user_id: str, session: dict, command: str) -> ChatOut:
    session["awaiting_period"] = "analysis"
    return ChatOut(
        reply="За какой период построить анализ?", quick_replies=QUICK_PERIODS
    )


def _ro_plot(user_id: str, session: dict, command: str) -> ChatOut:
    session["awaiting_period"] = "plot"
    return ChatOut(
        reply="За какой период построить график?", quick_replies=QUICK_PERIODS
    )


def _ro_table(user_id: str, session: dict, command: str) -> ChatOut:
    session["awaiting_table_days"] = True
    return _table_days_prompt()


def _ro_predict(user_id: str, session: dict, command: str) -> ChatOut:
    reply, images = analytics_service.run_predict(user_id)
    return ChatOut(reply=reply, images=images, quick_replies=READ_ONLY_MENU)


def _ro_allergy(user_id: str, session: dict, command: str) -> ChatOut:
    return ChatOut(
        reply=location_service.run_allergy_check(user_id), quick_replies=READ_ONLY_MENU
    )


def _ro_act_status(user_id: str, session: dict, command: str) -> ChatOut:
    return ChatOut(
        reply=act_service.show_act_status(user_id), quick_replies=READ_ONLY_MENU
    )


def _ro_plan_view(user_id: str, session: dict, command: str) -> ChatOut:
    return ChatOut(
        reply=treatment_plan_service.show_plan(user_id), quick_replies=READ_ONLY_MENU
    )


def _ro_report(user_id: str, session: dict, command: str) -> ChatOut:
    return ChatOut(
        reply="📄 Отчёт готов — откроется в новой вкладке.",
        quick_replies=READ_ONLY_MENU,
        download_url=f"/api/report/{user_id}",
    )


def _ro_export(user_id: str, session: dict, command: str) -> ChatOut:
    session["awaiting_period"] = "export"
    return ChatOut(
        reply="За какой период выгрузить данные?", quick_replies=QUICK_PERIODS
    )


def _ro_profile_view(user_id: str, session: dict, command: str) -> ChatOut:
    return ChatOut(
        reply=profile_service.show_profile(user_id), quick_replies=READ_ONLY_MENU
    )


_READ_ONLY_COMMANDS = {
    "analysis": _ro_analysis,
    "plot": _ro_plot,
    "table": _ro_table,
    "predict": _ro_predict,
    "allergy": _ro_allergy,
    "act_status": _ro_act_status,
    "plan_view": _ro_plan_view,
    "report": _ro_report,
    "export": _ro_export,
    "profile_view": _ro_profile_view,
}


def _process_read_only(
    user_id: str, session: dict, t: str, tl: str, command: str | None
) -> ChatOut:
    if tl in GREETINGS or tl in HELP_WORDS:
        session["awaiting_period"] = None
        session["awaiting_table_days"] = False
        return ChatOut(reply=read_only_welcome(), quick_replies=READ_ONLY_MENU)

    if command:
        cmd_id = command.split(":", 1)[0]
        handler = _READ_ONLY_COMMANDS.get(cmd_id)
        if handler:
            session["awaiting_period"] = None
            session["awaiting_table_days"] = False
            return handler(user_id, session, command)

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

    return ChatOut(reply=read_only_notice(), quick_replies=READ_ONLY_MENU)
