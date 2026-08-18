import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

POLLEN_VARS = [
    "alder_pollen",
    "birch_pollen",
    "grass_pollen",
    "mugwort_pollen",
    "olive_pollen",
    "ragweed_pollen",
]

POLLEN_RU = {
    "alder_pollen": "ольха",
    "birch_pollen": "берёза",
    "grass_pollen": "злаковые травы",
    "mugwort_pollen": "полынь",
    "olive_pollen": "олива",
    "ragweed_pollen": "амброзия",
}


def parse_allergen_selection(text: str) -> list:
    lower = text.lower()
    found = []
    for key, label in POLLEN_RU.items():
        if label.lower() in lower or label.lower().replace("ё", "е") in lower:
            found.append(key)
    return found


REQUEST_TIMEOUT = 8


def geocode_city(name: str):
    try:
        r = requests.get(
            GEOCODING_URL,
            params={"name": name, "count": 1, "language": "ru", "format": "json"},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return None

    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    label = ", ".join(
        filter(None, [top.get("name"), top.get("admin1"), top.get("country")])
    )
    return {"lat": top["latitude"], "lon": top["longitude"], "label": label}


def get_today_pollen(lat: float, lon: float):
    try:
        r = requests.get(
            AIR_QUALITY_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(POLLEN_VARS + ["european_aqi"]),
                "forecast_days": 1,
                "timezone": "auto",
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return None

    hourly = data.get("hourly") or {}
    if "time" not in hourly:
        return None

    result = {}
    for var in POLLEN_VARS + ["european_aqi"]:
        values = [v for v in (hourly.get(var) or []) if v is not None]
        if values:
            # Пиковое значение за день важнее для оценки риска аллергии, чем среднее.
            result[var] = max(values)
    return result or None


def _risk_level(value: float):
    if value < 10:
        return "низкий"
    if value < 50:
        return "умеренный"
    if value < 200:
        return "высокий"
    return "очень высокий"


def summarize_pollen(pollen_data: dict, user_allergens: list | None = None) -> str:
    """Короткая сводка по пыльце для утреннего уведомления/команды 'аллергия'.

    Если известны собственные аллергии пользователя (user_allergens — ключи из
    POLLEN_VARS), для них показываем уровень всегда, даже умеренный
    """
    if not pollen_data or not any(var in pollen_data for var in POLLEN_VARS):
        return "Нет данных о пыльце для вашего региона (сервис пока покрывает в основном Европу)."

    user_allergens = set(user_allergens or [])
    personal_lines = []
    other_lines = []
    for var in POLLEN_VARS:
        value = pollen_data.get(var)
        if value is None:
            continue
        level = _risk_level(value)
        line = f"{POLLEN_RU[var]} — {level} ({value:.0f} гран/м³)"
        if var in user_allergens:
            personal_lines.append(line)
        elif level in ("высокий", "очень высокий"):
            other_lines.append(line)

    if not personal_lines and not other_lines:
        return "🌿 Уровень пыльцы сегодня низкий/умеренный — существенных рисков не ожидается."

    parts = []
    if personal_lines:
        parts.append(
            "🌸 Ваши аллергены сегодня:\n"
            + "\n".join(f"  • {l}" for l in personal_lines)
        )
    if other_lines:
        parts.append(
            "Также повышен уровень:\n" + "\n".join(f"  • {l}" for l in other_lines)
        )
    return "\n".join(parts)
