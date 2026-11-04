import re
from datetime import datetime, timedelta

ALL_TIME = -1

# Единый источник истины для "утро"/"вечер" — используется и при записи
# показаний (logging_service.py: до этого часа — только показания, без
# препаратов/приступов/состояния), и при отображении (analytics_service.py,
# forecast_service.py, table_service.py), чтобы деление было одинаковым везде.
MORNING_CUTOFF_HOUR = 12
PERIOD_RU = {"morning": "утро", "evening": "вечер"}


def classify_period(date_value) -> str:
    """'morning', если час записи меньше MORNING_CUTOFF_HOUR, иначе 'evening'.
    Принимает и datetime/pd.Timestamp (есть атрибут .hour), и строку в
    формате БД "%Y-%m-%d %H:%M:%S" (час — по фиксированной позиции 11:13)."""
    hour = (
        date_value.hour if hasattr(date_value, "hour") else int(str(date_value)[11:13])
    )
    return "morning" if hour < MORNING_CUTOFF_HOUR else "evening"


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
EARLIEST_POSSIBLE_DATE = datetime(1970, 1, 1)


def parse_period(text: str):
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
