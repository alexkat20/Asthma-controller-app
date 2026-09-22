import re

from repositories.extra_info_repository import EXTRA_INFO_FLAGS

STATE_KEYWORDS = {
    # --- триггеры -----------------------------------------------------
    "sport": [
        "спорт",
        "трениров",
        "пробеж",
        "бег",
        "качалк",
        "зал",
        "плаван",
        "футбол",
        "баскетбол",
        "велосипед",
        "фитнес",
        "нагрузк",
        "sport",
        "training",
        "gym",
        "workout",
        "run",
    ],
    "sickness": [
        "болел",
        "болезнь",
        "простуд",
        "температур",
        "орви",
        "просты",
        "грипп",
        "недомога",
        "заболел",
        "sick",
        "sickness",
        "ill",
        "flu",
        "cold",
    ],
    "stress": [
        "стресс",
        "нерв",
        "переутомл",
        "тревог",
        "паник",
        "экзамен",
        "устал",
        "перенапряж",
        "stress",
        "tired",
        "anxiety",
    ],
    "allergy": [
        "аллерг",
        "пыльц",
        "цвет",
        "чихан",
        "насморк",
        "поллино",
        "allergy",
        "allergic",
        "pollen",
    ],
    "flight": [
        "перелет",
        "перелёт",
        "самолет",
        "самолёт",
        "полет",
        "полёт",
        "авиа",
        "flight",
        "plane",
    ],
    "weather": [
        "погод",
        "холод",
        "мороз",
        "ветер",
        "дожд",
        "сырост",
        "влажност",
        "weather",
        "cold air",
        "wind",
    ],
    "smoke": [
        "дым",
        "курени",
        "накурен",
        "сигарет",
        "smoke",
        "smoking",
    ],
    "strong_smells": [
        "запах",
        "духи",
        "парфюм",
        "бытовая хими",
        "чистящ",
        "spray",
        "perfume",
        "chemical smell",
    ],
    "pets": [
        "кошк",
        "кот",
        "собак",
        "шерст",
        "питомц",
        "pet",
        "cat",
        "dog",
    ],
    "dust": [
        "пыль",
        "dust",
    ],
    "menstrual_cycle": [
        "менструац",
        "месячны",
        "пмс",
        "цикл",
        "period",
        "menstrual",
    ],
    # --- симптомы -------------------------------------------------------
    "dyspnea": [
        "одышк",
        "нехватк воздух",
        "не хватает воздух",
        "тяжело дыш",
        "dyspnea",
        "breathless",
        "shortness of breath",
    ],
    "cough": [
        "кашел",
        "кашл",
        "cough",
    ],
    "wheezing": [
        "хрип",
        "свист",
        "wheez",
    ],
    "chest_tightness": [
        "заложенност",
        "давит в груди",
        "стеснен",  # основа: «стеснение/стеснения в груди»
        "тяжесть в груди",
        "chest tightness",
        "tight chest",
    ],
    "nocturnal_symptoms": [
        "просыпал",
        "будил",
        "не спал из-за",
        "ночью не",
        "nocturnal",
        "woke up at night",
    ],
}

NEGATION_WORDS = ["не", "без", "нет", "никакого", "никакой", "no", "not", "without"]
NEGATION_WINDOW_CHARS = 15
FLAG_ORDER = EXTRA_INFO_FLAGS

MEDICINE_ALIASES = {
    "симбикорт": "Symbicort Turbuhaler",
    "турбухалер": "Symbicort Turbuhaler",
    "сальбутамол": "Salbutamol",
    "вентолин": "Salbutamol",
    "релвар": "Relvar Ellipta",
    "эллипта": "Relvar Ellipta",
    "пульмикорт": "Pulmicort",
    "формисонид": "Formisonid",
    "формотерол": "Formisonid",
}

DOSE_UNIT_PATTERN = re.compile(
    r"(?:мг|мкг|mg|mcg|доз[аиы]?|вдох|puff|puffs|раз[а]?)", re.IGNORECASE
)


def detect_state(text: str) -> dict:
    flags = {f: False for f in FLAG_ORDER}
    if not text:
        return flags

    lower = text.lower()
    for flag, keywords in STATE_KEYWORDS.items():
        for kw in keywords:
            idx = lower.find(kw)
            if idx == -1:
                continue
            window_start = max(0, idx - NEGATION_WINDOW_CHARS)
            window_end = min(len(lower), idx + len(kw) + NEGATION_WINDOW_CHARS)
            surrounding = (
                lower[window_start:idx] + " " + lower[idx + len(kw) : window_end]
            )
            negated = any(
                re.search(rf"\b{neg}\b", surrounding) for neg in NEGATION_WORDS
            )
            if not negated:
                flags[flag] = True
            break
    return flags


def _find_medicine_mentions(lower_text: str, known_medicines: list[str]) -> list[dict]:
    mentions = []
    used_spans = []

    def overlaps(span):
        return any(not (span[1] <= s[0] or span[0] >= s[1]) for s in used_spans)

    for alias, canonical in MEDICINE_ALIASES.items():
        idx = lower_text.find(alias)
        if idx != -1:
            span = (idx, idx + len(alias))
            if not overlaps(span):
                exact = next(
                    (m for m in known_medicines if m.lower() == canonical.lower()),
                    canonical,
                )
                mentions.append({"name": exact, "span": span})
                used_spans.append(span)

    for med in known_medicines:
        for token in med.lower().split():
            if len(token) < 4:
                continue
            idx = lower_text.find(token)
            if idx != -1:
                span = (idx, idx + len(token))
                if not overlaps(span):
                    mentions.append({"name": med, "span": span})
                    used_spans.append(span)
                break

    return mentions


def _find_dose_near(text: str, span: tuple, window: int = 15) -> int:
    start = max(0, span[0] - window)
    end = min(len(text), span[1] + window)
    nearby = text[start:end]
    for match in re.finditer(r"\b(\d{1,2})\b", nearby):
        value = int(match.group(1))
        if 1 <= value <= 10:
            return value
    return 1  # по умолчанию — один приём


def extract_peak_flow_values(text: str) -> list:
    values = []
    for match in re.finditer(r"(?<!\d)(\d{3})(?!\d)", text):
        start, end = match.span()
        context_after = text[end : end + 6]
        if re.match(
            r"^\s{0,2}" + DOSE_UNIT_PATTERN.pattern, context_after, re.IGNORECASE
        ):
            continue
        value = int(match.group(1))
        if 100 <= value <= 900:
            values.append(value)
    return values


def parse_log_message(text: str, known_medicines: list) -> dict:
    known_medicines = known_medicines or []
    peak_flow = extract_peak_flow_values(text)
    flags = detect_state(text)

    lower = text.lower()
    mentions = _find_medicine_mentions(lower, known_medicines)
    medicines = []
    seen_names = set()
    for m in mentions:
        if m["name"] in seen_names:
            continue
        seen_names.add(m["name"])
        dose = _find_dose_near(text, m["span"])
        medicines.append({"name": m["name"], "dose": dose})

    return {
        "peak_flow": peak_flow,
        "medicines": medicines,
        "flags": flags,
        "raw_text": text,
    }
