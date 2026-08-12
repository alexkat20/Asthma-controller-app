"""Разбор периодов ('неделя', '2 недели', произвольный диапазон дат) для анализа/графиков/экспорта."""

import re
from datetime import datetime, timedelta

ALL_TIME = (
    -1
)  # сентинел для «всё время»: отдельно от None, который означает «период не распознан»

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
    "всё время": ALL_TIME,
    "все время": ALL_TIME,
    "всё": ALL_TIME,
    "all": ALL_TIME,
}
QUICK_PERIODS = ["Неделя", "2 недели", "Месяц", "Квартал", "Год", "Всё время"]

CUSTOM_RANGE_RE = re.compile(
    r"(\d{1,2}\.\d{1,2}\.\d{4})\s*[-–—]\s*(\d{1,2}\.\d{1,2}\.\d{4})"
)

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
EARLIEST_POSSIBLE_DATE = datetime(
    1970, 1, 1
)  # для периода "всё время" — нижняя граница без верхнего предела


def parse_period(text: str):
    """Возвращает (days, None) для именованного периода (days=ALL_TIME означает
    'всё время') или (None, (start, end)) для произвольного диапазона дат.
    (None, None) — период не распознан."""
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
    """
    Возвращает (start_str, end_str, человекочитаемая_метка_периода) — обе
    границы уже посчитаны в Python и отформатированы как обычные строки
    "%Y-%m-%d %H:%M:%S". Раньше здесь собиралась SQLite-специфичная
    SQL-строка с функцией datetime('now', ?), которая работала только на
    SQLite — на PostgreSQL синтаксис вычисления интервалов другой. Вычисляя
    границы в Python и сравнивая обычные строки (формат лексикографически
    сортируется), код работает одинаково на обоих бэкендах без каких-либо
    SQL-функций, специфичных для диалекта.
    """
    if custom_range:
        start, end = custom_range
        return (
            start.strftime("%Y-%m-%d 00:00:00"),
            end.strftime("%Y-%m-%d 23:59:59"),
            f"{start.date().strftime('%d.%m.%Y')}—{end.date().strftime('%d.%m.%Y')}",
        )

    end = datetime.now()
    if days == ALL_TIME:
        start = EARLIEST_POSSIBLE_DATE
        label = "всё время"
    else:
        start = end - timedelta(days=days)
        label = {
            7: "неделя",
            14: "2 недели",
            30: "месяц",
            90: "квартал",
            365: "год",
        }.get(days, f"{days} дн.")

    return start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT), label
