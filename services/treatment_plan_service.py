from datetime import datetime

from models.schemas import ChatOut
from repositories import treatment_plan_repository as plan_repo
from utils.formatting import MAIN_MENU

PLAN_ORDER = ["baseline_therapy", "worsening_therapy", "attack_therapy"]
PLAN_PROMPTS = {
    "baseline_therapy": "Базовая терапия — что принимать регулярно по назначению врача (независимо от самочувствия)?",
    "worsening_therapy": "Что делать при ухудшении состояния (жёлтая зона)? Например, какой препарат добавить и в какой дозе.",
    "attack_therapy": "Что делать при приступе (красная зона)? Например, экстренный препарат, доза, когда вызывать скорую.",
}
PLAN_LABELS = {
    "baseline_therapy": "Базовая терапия",
    "worsening_therapy": "При ухудшении (жёлтая зона)",
    "attack_therapy": "При приступе (красная зона)",
}


def start_plan_edit(session: dict) -> ChatOut:
    session["plan_step"] = PLAN_ORDER[0]
    session["plan_data"] = {}
    return ChatOut(reply=PLAN_PROMPTS[PLAN_ORDER[0]], quick_replies=["Пропустить"])


def continue_plan_edit(user_id: str, session: dict, text: str) -> ChatOut:
    step = session["plan_step"]
    if "пропуст" not in text.strip().lower():
        session.setdefault("plan_data", {})[step] = text.strip()

    idx = PLAN_ORDER.index(step)
    if idx + 1 < len(PLAN_ORDER):
        next_step = PLAN_ORDER[idx + 1]
        session["plan_step"] = next_step
        return ChatOut(reply=PLAN_PROMPTS[next_step], quick_replies=["Пропустить"])

    data = session.pop("plan_data", {})
    session["plan_step"] = None

    plan_repo.save_plan(user_id, data, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    return ChatOut(
        reply="План лечения сохранён.\n\n" + show_plan(user_id), quick_replies=MAIN_MENU
    )


def show_plan(user_id: str) -> str:
    plan = plan_repo.get_plan(user_id)

    if plan is None or not any(plan.get(k) for k in PLAN_ORDER):
        return "План лечения ещё не задан. Напишите «план лечения», чтобы заполнить."

    lines = []
    for key in PLAN_ORDER:
        value = plan.get(key)
        lines.append(f"{PLAN_LABELS[key]}: {value or 'не указано'}")
    return "\n".join(lines)


def get_guidance_for_zone(user_id: str, zone: str) -> str | None:
    field = {"yellow": "worsening_therapy", "red": "attack_therapy"}.get(zone)
    if field is None:
        return None
    plan = plan_repo.get_plan(user_id)
    if plan is None:
        return None
    return plan.get(field)


def get_attack_guidance(user_id: str) -> str | None:
    plan = plan_repo.get_plan(user_id)
    if plan is None:
        return None
    return plan.get("attack_therapy")
