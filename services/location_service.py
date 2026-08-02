"""
Местоположение пользователя (для сводки по пыльце) и проверка аллергии "сейчас".

Оркестрирует repositories.settings_repository (хранение) и services.allergy_service
(геокодинг города + получение данных о пыльце через внешний Open-Meteo API).
"""

from repositories import settings_repository as settings_repo
from repositories.database import get_connection
from repositories.profile_repository import get_profile
from services import allergy_service


def set_user_location(user_id: str, city_text: str) -> str:
    geo = allergy_service.geocode_city(city_text)
    if geo is None:
        return (
            f"Не нашёл город «{city_text}». Проверьте написание или укажите ближайший крупный город "
            "(например: «город Berlin» или «город Санкт-Петербург»)."
        )
    conn = get_connection()
    settings_repo.save_user_location(
        conn, user_id, geo["label"], geo["lat"], geo["lon"]
    )
    conn.close()
    return f"📍 Город сохранён: {geo['label']}. Буду учитывать пыльцу для этого региона в утренних уведомлениях."


def get_user_location(user_id: str):
    conn = get_connection()
    loc = settings_repo.get_user_location(conn, user_id)
    conn.close()
    return loc


def run_allergy_check(user_id: str) -> str:
    loc = get_user_location(user_id)
    if loc is None:
        return (
            "Сначала укажите город, чтобы я мог проверить пыльцу в вашем регионе: "
            "напишите, например, «город Москва»."
        )
    profile = get_profile(user_id)
    user_allergens = profile["allergies"] if profile else None
    pollen = allergy_service.get_today_pollen(loc["lat"], loc["lon"])
    return (
        f"📍 {loc['label']}\n{allergy_service.summarize_pollen(pollen, user_allergens)}"
    )
