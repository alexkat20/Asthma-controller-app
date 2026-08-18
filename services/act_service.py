from datetime import datetime, timedelta

from models.schemas import ChatOut
from repositories import act_repository as act_repo
from repositories import profile_repository as profile_repo
from repositories.database import get_connection
from services import notification_service
from utils.formatting import MAIN_MENU

ACT_INTERVAL_DAYS = 30

ACT_QUESTIONS = [
    (
        "Как часто за последние 4 недели астма мешала вам заниматься обычными делами "
        "(работа, учёба, домашние дела)?",
        [
            ("Постоянно", 1),
            ("Очень часто", 2),
            ("Иногда", 3),
            ("Редко", 4),
            ("Ни разу", 5),
        ],
    ),
    (
        "Как часто за последние 4 недели у вас была одышка или нехватка воздуха?",
        [
            ("Чаще раза в день", 1),
            ("Раз в день", 2),
            ("3-6 раз в неделю", 3),
            ("1-2 раза в неделю", 4),
            ("Ни разу", 5),
        ],
    ),
    (
        "Как часто за последние 4 недели вы просыпались ночью или раньше обычного "
        "из-за симптомов астмы?",
        [
            ("4 и более ночей в неделю", 1),
            ("2-3 ночи в неделю", 2),
            ("Раз в неделю", 3),
            ("1-2 раза за 4 недели", 4),
            ("Ни разу", 5),
        ],
    ),
    (
        "Как часто за последние 4 недели вы пользовались препаратом скорой помощи "
        "(например, сальбутамолом)?",
        [
            ("3 и более раз в день", 1),
            ("1-2 раза в день", 2),
            ("2-3 раза в неделю", 3),
            ("Раз в неделю или реже", 4),
            ("Ни разу", 5),
        ],
    ),
    (
        "Как бы вы сами оценили контроль над астмой за последние 4 недели?",
        [
            ("Совсем не контролировал(а)", 1),
            ("Плохо контролировал(а)", 2),
            ("В некоторой степени", 3),
            ("Хорошо контролировал(а)", 4),
            ("Полностью контролировал(а)", 5),
        ],
    ),
]


def interpret_score(total: int) -> str:
    if total == 25:
        return "полный контроль над астмой"
    if total >= 20:
        return "хороший контроль над астмой"
    if total >= 16:
        return "недостаточный контроль — стоит обсудить с врачом терапию"
    return "очень плохой контроль — рекомендуется обратиться к врачу в ближайшее время"


def _next_due_date(user_id: str):
    conn = get_connection()
    last = act_repo.get_last_act(conn, user_id)
    conn.close()

    if last:
        base = datetime.fromisoformat(last["date"])
    else:
        created_at = profile_repo.get_created_at(user_id)
        if created_at is None:
            return None
        base = datetime.fromisoformat(created_at)
    return base + timedelta(days=ACT_INTERVAL_DAYS)


def is_act_due(user_id: str) -> bool:
    next_due = _next_due_date(user_id)
    return next_due is not None and datetime.now() >= next_due


def start_act(session: dict) -> ChatOut:
    session["act_step"] = 0
    session["act_answers"] = []
    question, options = ACT_QUESTIONS[0]
    return ChatOut(
        reply=f"Вопрос 1 из {len(ACT_QUESTIONS)}. {question}",
        quick_replies=[o[0] for o in options],
    )


def continue_act(user_id: str, session: dict, text: str) -> ChatOut:
    step = session.get("act_step", 0)
    question, options = ACT_QUESTIONS[step]
    key = text.strip().lower()

    score = next((s for label, s in options if label.lower() == key), None)
    if score is None:
        return ChatOut(
            reply="Выберите один из предложенных вариантов ответа.",
            quick_replies=[o[0] for o in options],
        )

    session.setdefault("act_answers", []).append(score)
    step += 1

    if step < len(ACT_QUESTIONS):
        session["act_step"] = step
        next_question, next_options = ACT_QUESTIONS[step]
        return ChatOut(
            reply=f"Вопрос {step + 1} из {len(ACT_QUESTIONS)}. {next_question}",
            quick_replies=[o[0] for o in next_options],
        )

    answers = session.pop("act_answers")
    session["act_step"] = None
    total = sum(answers)

    conn = get_connection()
    act_repo.save_act_result(
        conn, user_id, answers, total, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    previous = act_repo.get_act_history(conn, user_id, limit=2)
    conn.close()

    trend_line = ""
    if len(previous) >= 2:
        delta = previous[0]["total_score"] - previous[1]["total_score"]
        if delta > 0:
            trend_line = f"\nС прошлого раза лучше на {delta} балл(ов)."
        elif delta < 0:
            trend_line = f"\nС прошлого раза хуже на {abs(delta)} балл(ов)."
        else:
            trend_line = "\nБез изменений с прошлого раза."

    return ChatOut(
        reply=(
            f"Тест завершён. Ваш балл: {total} из 25 — {interpret_score(total)}.{trend_line}\n\n"
            "Следующий тест предложу примерно через месяц."
        ),
        quick_replies=MAIN_MENU,
    )


def show_act_status(user_id: str) -> str:
    conn = get_connection()
    last = act_repo.get_last_act(conn, user_id)
    conn.close()
    if last is None:
        return "Вы ещё не проходили тест контроля астмы. Напишите «тест контроля», чтобы пройти его сейчас."
    date_label = last["date"].split(" ")[0]
    return (
        f"Последний тест контроля астмы: {date_label}, балл {last['total_score']} из 25 "
        f"— {interpret_score(last['total_score'])}."
    )


def check_and_notify_due_users() -> None:
    """Вызывается из фонового планировщика (services/reminder_service.py)."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    for user_id in profile_repo.list_user_ids():
        if not is_act_due(user_id):
            continue
        conn = get_connection()
        already_notified_today = act_repo.get_last_notified(conn, user_id) == today_str
        if not already_notified_today:
            act_repo.mark_notified(conn, user_id, today_str)
        conn.close()
        if not already_notified_today:
            notification_service.push(
                user_id,
                "🩺 Пора пройти ежемесячный тест контроля астмы — займёт около минуты. "
                "Напишите «тест контроля», чтобы начать.",
            )
