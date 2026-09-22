"""Добавление/исправление пропущенного показания пикфлоуметрии.

В отличие от logging_service.py (запись «прямо сейчас», где время замера —
всегда текущий момент, а период определяется им автоматически), здесь
пользователь сам выбирает дату из прошлого и период (утро/вечер) — например,
чтобы задним числом добавить забытый вчерашний вечерний замер или исправить
опечатку в уже сохранённом значении.
"""

import re
from datetime import date as date_cls
from datetime import datetime, timedelta

from models.schemas import ChatOut
from repositories.unit_of_work import UnitOfWork
from utils.numbers import extract_numbers
from utils.formatting import MAIN_MENU, ZONE_RU

_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_PERIOD_QUICK_LABELS = {"morning": "🌅 Утро", "evening": "🌇 Вечер"}
_PERIOD_ADJ_RU = {"morning": "Утреннее", "evening": "Вечернее"}


def _extract_numbers(text: str) -> list:
    return extract_numbers(text)


def _parse_date(text: str) -> date_cls | None:
    t = text.strip().lower()
    today = datetime.now().date()
    if t in ("сегодня", "today"):
        return today
    if t in ("вчера", "yesterday"):
        return today - timedelta(days=1)
    if t in ("позавчера",):
        return today - timedelta(days=2)
    m = _DATE_RE.search(t)
    if m:
        day, month, year = (int(x) for x in m.groups())
        try:
            return date_cls(year, month, day)
        except ValueError:
            return None
    return None


def _period_quick_replies(user_id: str, day: date_cls) -> list:
    with UnitOfWork() as uow:
        existing = {
            period: uow.readings.find_reading(user_id, day, period)
            for period in ("morning", "evening")
        }
    labels = []
    for period in ("morning", "evening"):
        found = existing[period]
        suffix = f" ({found['maximum']:.0f})" if found else " (нет данных)"
        labels.append(_PERIOD_QUICK_LABELS[period] + suffix)
    return labels


def prompt_date(session: dict) -> ChatOut:
    session["log_step"] = "backfill_date"
    session["backfill_data"] = {}
    return ChatOut(
        reply=(
            "За какую дату добавить или исправить показание? Напишите "
            "«сегодня», «вчера» или дату в формате ДД.ММ.ГГГГ."
        ),
        quick_replies=["Сегодня", "Вчера"],
    )


def handle_date_step(user_id: str, session: dict, text: str) -> ChatOut:
    day = _parse_date(text)
    if day is None:
        return ChatOut(
            reply=(
                "Не понял дату. Напишите «сегодня», «вчера» или в формате "
                "ДД.ММ.ГГГГ, например 25.08.2026."
            ),
            quick_replies=["Сегодня", "Вчера"],
        )
    if day > datetime.now().date():
        return ChatOut(
            reply="Дата не может быть в будущем — укажите сегодняшнюю или прошедшую."
        )

    session["backfill_data"] = {"day": day.isoformat()}
    session["log_step"] = "backfill_period"
    return ChatOut(
        reply=f"Показание за {day.strftime('%d.%m.%Y')} — утреннее или вечернее?",
        quick_replies=_period_quick_replies(user_id, day),
    )


def handle_period_step(user_id: str, session: dict, text: str) -> ChatOut:
    tl = text.strip().lower()
    day = date_cls.fromisoformat(session["backfill_data"]["day"])
    if "утр" in tl:
        period = "morning"
    elif "вечер" in tl:
        period = "evening"
    else:
        return ChatOut(
            reply="Выберите «Утро» или «Вечер».",
            quick_replies=_period_quick_replies(user_id, day),
        )

    session["backfill_data"]["period"] = period
    session["log_step"] = "backfill_values"
    return ChatOut(
        reply="Введите три показания пикфлоуметра через пробел, например: 450 460 470."
    )


def handle_values_step(user_id: str, session: dict, text: str) -> ChatOut:
    numbers = _extract_numbers(text)
    if len(numbers) < 3:
        return ChatOut(
            reply=(
                "Не нашёл три числа. Введите три показания пикфлоуметра через "
                "пробел, например: 450 460 470."
            )
        )
    values = numbers[:3]
    data = session.pop("backfill_data", {})
    session["log_step"] = None
    day = date_cls.fromisoformat(data["day"])
    period = data["period"]

    with UnitOfWork() as uow:
        result = uow.readings.upsert_reading_for_period(user_id, day, period, *values)
        uow.commit()

    verb = "исправлено" if result["updated"] else "добавлено"
    zone_ru = ZONE_RU.get(result["zone"], "нет данных")
    reply = (
        f"✅ {_PERIOD_ADJ_RU[period]} показание за {day.strftime('%d.%m.%Y')} "
        f"{verb}: {', '.join(str(int(v)) for v in values)} "
        f"(максимум {result['maximum']:.0f}).\nЗона: {zone_ru}."
    )
    return ChatOut(reply=reply, quick_replies=MAIN_MENU)
