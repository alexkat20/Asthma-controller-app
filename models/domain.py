from dataclasses import dataclass


@dataclass
class ZoneThresholds:
    """Пороги зон пикфлоу для конкретного пользователя на конкретный момент времени."""

    personal_best: float
    green_zone: float  # нижняя граница зелёной зоны
    yellow_zone: float  # нижняя граница жёлтой зоны
    red_zone: float = 0.0  # нижняя граница красной зоны (всегда 0)


# Доли от персонального рекорда, задающие границы зон
GREEN_RATIO = 0.8
YELLOW_RATIO = 0.5


def thresholds_from_personal_best(personal_best: float) -> ZoneThresholds:
    return ZoneThresholds(
        personal_best=personal_best,
        green_zone=round(personal_best * GREEN_RATIO, 1),
        yellow_zone=round(personal_best * YELLOW_RATIO, 1),
        red_zone=0.0,
    )


def classify_zone(maximum: float, thresholds: ZoneThresholds | None) -> str:
    """Чистая доменная логика: к какой зоне относится показание при данных порогах."""
    if thresholds is None:
        return "unknown"
    if maximum >= thresholds.green_zone:
        return "green"
    if maximum >= thresholds.yellow_zone:
        return "yellow"
    return "red"
