import re

from models.schemas import ChatOut
from repositories.unit_of_work import UnitOfWork
from services import act_service, allergy_service, location_service
from utils.formatting import GENDER_RU, SMOKING_RU, welcome_text

ONBOARDING_ORDER = ["gender", "age", "height", "weight", "smoking", "city", "allergies"]
ONBOARDING_PROMPTS = {
    "gender": (
        "Для начала — коротко о вас (один раз, займёт минуту). Это поможет точнее оценивать состояние.\n\nВаш пол?",
        ["Мужской", "Женский", "Не указывать"],
    ),
    "age": ("Сколько вам лет?", ["Пропустить"]),
    "height": ("Ваш рост, см?", ["Пропустить"]),
    "weight": ("Ваш вес, кг?", ["Пропустить"]),
    "smoking": ("Курите?", ["Не курю", "Курю", "Бросил(а)"]),
    "city": (
        "В каком городе вы находитесь? Это нужно для утренней сводки по пыльце.",
        ["Пропустить"],
    ),
    "allergies": (
        "Есть ли у вас аллергия на пыльцу? Можем отслеживать: "
        + ", ".join(allergy_service.POLLEN_RU.values())
        + ".\nПеречислите через запятую, что подходит, или «нет».",
        ["Нет аллергии"],
    ),
}


def _extract_number(text: str):
    m = re.search(r"\d+(?:[.,]\d+)?", text)
    if not m:
        return None
    return float(m.group(0).replace(",", "."))


def start_onboarding(session: dict) -> ChatOut:
    session["onboarding_step"] = ONBOARDING_ORDER[0]
    session["onboarding_data"] = {}
    prompt, options = ONBOARDING_PROMPTS[ONBOARDING_ORDER[0]]
    return ChatOut(reply=prompt, quick_replies=options)


def summarize_profile(data: dict, location_label: str | None = None) -> str:
    lines = [
        f"Пол: {GENDER_RU.get(data.get('gender'), 'не указан')}",
        f"Возраст: {data.get('age') or 'не указан'}",
        f"Рост: {data.get('height_cm') or 'не указан'} см"
        if data.get("height_cm")
        else "Рост: не указан",
        f"Вес: {data.get('weight_kg') or 'не указан'} кг"
        if data.get("weight_kg")
        else "Вес: не указан",
        f"Курение: {SMOKING_RU.get(data.get('smoking'), 'не указано')}",
    ]
    allergens = data.get("allergies") or []
    lines.append(
        "Аллергия на пыльцу: "
        + (
            ", ".join(allergy_service.POLLEN_RU[a] for a in allergens)
            if allergens
            else "не указана"
        )
    )
    if location_label:
        lines.append(f"Город: {location_label}")
    return "\n".join(lines)


def continue_onboarding(user_id: str, session: dict, text: str) -> ChatOut:
    step = session["onboarding_step"]
    data = session.setdefault("onboarding_data", {})
    tl = text.strip().lower()
    skip = "пропуст" in tl

    if step == "gender":
        data["gender"] = "male" if "муж" in tl else "female" if "жен" in tl else None
    elif step == "age":
        data["age"] = None if skip else _extract_number(text)
        if data["age"] is not None:
            data["age"] = int(data["age"])
    elif step == "height":
        data["height_cm"] = None if skip else _extract_number(text)
    elif step == "weight":
        data["weight_kg"] = None if skip else _extract_number(text)
    elif step == "smoking":
        data["smoking"] = (
            "no"
            if "не кур" in tl
            else "quit"
            if "брос" in tl
            else "yes"
            if "кур" in tl
            else None
        )
    elif step == "city":
        data["city_text"] = None if skip else text.strip()
    elif step == "allergies":
        data["allergies"] = (
            []
            if (skip or "нет" in tl)
            else allergy_service.parse_allergen_selection(text)
        )

    idx = ONBOARDING_ORDER.index(step)
    if idx + 1 < len(ONBOARDING_ORDER):
        next_step = ONBOARDING_ORDER[idx + 1]
        session["onboarding_step"] = next_step
        prompt, options = ONBOARDING_PROMPTS[next_step]
        return ChatOut(reply=prompt, quick_replies=options)

    session["onboarding_step"] = None
    with UnitOfWork() as uow:
        uow.profiles.save_profile(user_id, data)
        uow.commit()

    location_reply = None
    location_label = None
    if data.get("city_text"):
        location_reply = location_service.set_user_location(user_id, data["city_text"])
        loc = location_service.get_user_location(user_id)
        location_label = loc["label"] if loc else None
    session.pop("onboarding_data", None)

    reply = f"Профиль сохранён:\n\n{summarize_profile(data, location_label)}"
    if location_reply:
        reply += f"\n\n{location_reply}"
    reply += "\n\n" + welcome_text()
    reply += (
        "\n\nТеперь пройдём короткий тест контроля астмы — это займёт около минуты и станет "
        "точкой отсчёта (дальше буду предлагать его раз в месяц)."
    )
    act_prompt = act_service.start_act(session)
    return ChatOut(
        reply=reply + "\n\n" + act_prompt.reply, quick_replies=act_prompt.quick_replies
    )


def show_profile(user_id: str) -> str:
    with UnitOfWork() as uow:
        profile = uow.profiles.get_profile(user_id)
    if profile is None:
        return "Профиль ещё не заполнен."
    loc = location_service.get_user_location(user_id)
    return (
        summarize_profile(profile, loc["label"] if loc else None)
        + "\n\nЧтобы изменить — напишите «изменить профиль»."
    )
