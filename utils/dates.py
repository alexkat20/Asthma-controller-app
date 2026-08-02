"""Разбор периодов ('неделя', '2 недели', произвольный диапазон дат) для анализа/графиков."""

import re
from datetime import datetime

PERIOD_DAYS = {
    "неделя": 7,
    "неделю": 7,
    "week": 7,
    "2 недели": 14,
    "2недели": 14,
    "две недели": 14,
    "месяц": 30,
    "month": 30,
    "квартал": 90,
    "3 месяца": 90,
    "quarter": 90,
    "год": 365,
    "year": 365,
}
QUICK_PERIODS = ["Неделя", "2 недели", "Месяц", "Квартал", "Год"]

CUSTOM_RANGE_RE = re.compile(
    r"(\d{1,2}\.\d{1,2}\.\d{4})\s*[-–—]\s*(\d{1,2}\.\d{1,2}\.\d{4})"
)


def parse_period(text: str):
    """Возвращает (days, None) для именованного периода или (None, (start, end)) для диапазона дат."""
    t = text.strip().lower()
    if t in PERIOD_DAYS:
        return PERIOD_DAYS[t], None
    m = CUSTOM_RANGE_RE.search(t)
    if m:
        try:
            start = datetime.strptime(m.group(1), "%d.%m.%Y")
            end = datetime.strptime(m.group(2), "%d.%m.%Y")
            return None, (start, end)
        except ValueError:
            return None, None
    return None, None


def build_date_filter(days, custom_range):
    """Возвращает (where_clause, params, человекочитаемая_метка_периода)."""
    if custom_range:
        start, end = custom_range
        return (
            "date >= ? AND date <= ?",
            (start.strftime("%Y-%m-%d 00:00:00"), end.strftime("%Y-%m-%d 23:59:59")),
            f"{start.date().strftime('%d.%m.%Y')}—{end.date().strftime('%d.%m.%Y')}",
        )
    return (
        "date >= datetime('now', ?)",
        (f"-{days} days",),
        {7: "неделю", 14: "2 недели", 30: "месяц", 90: "квартал", 365: "год"}.get(
            days, f"{days} дн."
        ),
    )


def adapt_where_for_alias(where_clause: str, alias: str) -> str:
    """Подставляет алиас таблицы перед 'date' в WHERE-условии (не трогая 'datetime(...)').

    Например: "date >= datetime('now', ?)" -> "tm.date >= datetime('now', ?)"
    Наивный str.replace здесь сломал бы 'datetime(...)' на 'tm.datetime(...)' —
    поэтому используется regex с границей слова.
    """
    return re.sub(r"(?<![a-z])date(?![a-z])", f"{alias}.date", where_clause)
