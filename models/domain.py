from dataclasses import dataclass


@dataclass
class ZoneThresholds:
    """Пороги зон пикфлоу для конкретного пользователя на конкретный момент времени."""

    personal_best: float
    green_zone: float  # нижняя граница зелёной зоны
    yellow_zone: float  # нижняя граница жёлтой зоны
    red_zone: float = 0.0  # нижняя граница красной зоны (всегда 0)
