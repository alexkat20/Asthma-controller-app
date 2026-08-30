from models.schemas import QuickReply

ZONE_RU = {
    "green": "🟢 зелёная",
    "yellow": "🟡 жёлтая",
    "red": "🔴 красная",
    "unknown": "нет данных",
}
FLAG_RU = {
    # Триггеры
    "sport": "спорт",
    "sickness": "болезнь",
    "stress": "стресс",
    "allergy": "аллергия",
    "flight": "перелёт",
    "weather": "погода/холодный воздух",
    "smoke": "дым",
    "strong_smells": "резкие запахи/химия",
    "pets": "домашние животные",
    "dust": "пыль",
    "menstrual_cycle": "менструальный цикл",
    # Симптомы
    "dyspnea": "одышка",
    "cough": "кашель",
    "wheezing": "хрипы/свист при дыхании",
    "chest_tightness": "заложенность в груди",
    "nocturnal_symptoms": "ночные симптомы",
}
GENDER_RU = {"male": "мужской", "female": "женский", None: "не указан"}
SMOKING_RU = {"no": "не курит", "yes": "курит", "quit": "бросил(а)", None: "не указано"}

MAIN_MENU = [
    QuickReply(label="📝 Записать показания", command="log_reading"),
    QuickReply(label="📊 Анализ", command="analysis"),
    QuickReply(label="📈 График", command="plot"),
    QuickReply(label="🗓 Таблица", command="table"),
    QuickReply(label="🔮 Прогноз", command="predict"),
    QuickReply(label="🌸 Аллергия", command="allergy"),
    QuickReply(label="💊 Добавить лекарство", command="add_medicine"),
    QuickReply(label="⏰ Напоминание", command="reminder"),
    QuickReply(label="🩺 Тест контроля", command="act_test"),
    QuickReply(label="📋 План лечения", command="plan_view"),
    QuickReply(label="📄 Отчёт врачу", command="report"),
    QuickReply(label="⬇️ Экспорт данных", command="export"),
    QuickReply(label="👪 Семейный доступ", command="family_share"),
    QuickReply(label="👤 Профиль", command="profile_view"),
]

READ_ONLY_MENU = [
    QuickReply(label="📊 Анализ", command="analysis"),
    QuickReply(label="📈 График", command="plot"),
    QuickReply(label="🗓 Таблица", command="table"),
    QuickReply(label="🔮 Прогноз", command="predict"),
    QuickReply(label="🌸 Аллергия", command="allergy"),
    QuickReply(label="🩺 Статус теста", command="act_status"),
    QuickReply(label="📋 План лечения", command="plan_view"),
    QuickReply(label="📄 Отчёт врачу", command="report"),
    QuickReply(label="⬇️ Экспорт данных", command="export"),
    QuickReply(label="👤 Профиль", command="profile_view"),
]


def read_only_notice() -> str:
    return (
        "👪 Это режим семейного доступа — только просмотр. Записывать показания, менять "
        "профиль, препараты, напоминания и город отсюда нельзя.\n\n"
        "Нажмите одну из кнопок ниже — анализ, график, прогноз, аллергия, статус теста "
        "контроля, план лечения, отчёт, экспорт, профиль."
    )


def read_only_welcome(owner_label: str = "") -> str:
    who = f" пациента «{owner_label}»" if owner_label else ""
    return (
        f"👪 Вы просматриваете данные{who} в режиме только для чтения.\n\n"
        "Выберите нужное кнопкой ниже."
    )


def welcome_text() -> str:
    return (
        "Привет! Я слежу за вашей пикфлоуметрией.\n\n"
        "Чтобы записать показания, нажмите «Записать показания» или просто пришлите три "
        "числа (например: 450 460 470) — дальше я предложу выбрать препарат и дозу кнопками.\n\n"
        "Всё остальное — тоже кнопками ниже: анализ, график, таблица, прогноз, аллергия, "
        "препараты, план лечения от врача, напоминания, тест контроля астмы, отчёт и "
        "экспорт для визита к врачу, семейный доступ, профиль. Загрузка истории файлом — "
        "кнопка ⬆ вверху."
    )


def help_text() -> str:
    return (
        "Не совсем понял сообщение — но это не страшно, здесь всё через кнопки, набирать "
        "текстом команды не нужно (кроме показаний пикфлоуметра — их можно прислать прямо "
        "числами, например: 450 460 470).\n\n"
        "Нажмите нужную кнопку ниже, или «Помощь»/«Меню», чтобы увидеть их снова."
    )
