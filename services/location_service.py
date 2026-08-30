from repositories.unit_of_work import UnitOfWork
from services import allergy_service


def set_user_location(user_id: str, city_text: str) -> str:
    geo = allergy_service.geocode_city(city_text)
    if geo is None:
        return (
            f"Не нашёл город «{city_text}». Проверьте написание или укажите ближайший крупный город "
            "(например: «город Berlin» или «город Санкт-Петербург»)."
        )
    with UnitOfWork() as uow:
        uow.settings.save_user_location(user_id, geo["label"], geo["lat"], geo["lon"])
        uow.commit()
    return f"📍 Город сохранён: {geo['label']}. Буду учитывать пыльцу для этого региона в утренних уведомлениях."


def get_user_location(user_id: str):
    with UnitOfWork() as uow:
        return uow.settings.get_user_location(user_id)


def run_allergy_check(user_id: str) -> str:
    loc = get_user_location(user_id)
    if loc is None:
        return (
            "Сначала укажите город, чтобы я мог проверить пыльцу в вашем регионе: "
            "напишите, например, «город Москва»."
        )
    with UnitOfWork() as uow:
        profile = uow.profiles.get_profile(user_id)
    user_allergens = profile["allergies"] if profile else None
    pollen = allergy_service.get_today_pollen(loc["lat"], loc["lon"])
    return (
        f"📍 {loc['label']}\n{allergy_service.summarize_pollen(pollen, user_allergens)}"
    )
