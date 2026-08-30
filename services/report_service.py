from datetime import datetime

import pandas as pd

from repositories import act_repository as act_repo
from repositories import medicine_repository, reading_repository
from repositories import profile_repository as profile_repo
from services import analytics_service
from utils.dates import build_date_filter
from utils.formatting import GENDER_RU, SMOKING_RU

REPORT_PERIOD_DAYS = 90

_ALLERGY_RU = {
    "alder_pollen": "ольха",
    "birch_pollen": "берёза",
    "grass_pollen": "злаковые травы",
    "mugwort_pollen": "полынь",
    "olive_pollen": "олива",
    "ragweed_pollen": "амброзия",
}


def _profile_block(user_id: str) -> str:
    profile = profile_repo.get_profile(user_id)
    if profile is None:
        return "<p>Профиль не заполнен.</p>"
    allergens = profile.get("allergies") or []
    allergens_label = (
        ", ".join(_ALLERGY_RU.get(a, a) for a in allergens)
        if allergens
        else "не указана"
    )
    rows = [
        ("Пол", GENDER_RU.get(profile.get("gender"), "не указан")),
        ("Возраст", profile.get("age") or "не указан"),
        (
            "Рост",
            f"{profile['height_cm']} см" if profile.get("height_cm") else "не указан",
        ),
        (
            "Вес",
            f"{profile['weight_kg']} кг" if profile.get("weight_kg") else "не указан",
        ),
        ("Курение", SMOKING_RU.get(profile.get("smoking"), "не указано")),
        ("Аллергия на пыльцу", allergens_label),
    ]
    return (
        "<table>"
        + "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
        + "</table>"
    )


def _zone_block(user_id: str) -> str:
    thresholds = reading_repository.calculate_zone_thresholds(user_id, datetime.now())
    if thresholds is None:
        return "<p>Недостаточно данных для расчёта зон.</p>"
    return (
        "<table>"
        f"<tr><th>Персональный рекорд (90 дн.)</th><td>{thresholds.personal_best:.0f}</td></tr>"
        f"<tr><th>Зелёная зона</th><td>≥ {thresholds.green_zone:.0f}</td></tr>"
        f"<tr><th>Жёлтая зона</th><td>{thresholds.yellow_zone:.0f}–{thresholds.green_zone:.0f}</td></tr>"
        f"<tr><th>Красная зона</th><td>&lt; {thresholds.yellow_zone:.0f}</td></tr>"
        "</table>"
    )


def _medicine_usage_block(user_id: str, days: int) -> str:
    start_str, end_str, _ = build_date_filter(days, None)
    meds = medicine_repository.fetch_medicine_doses_df(user_id, start_str, end_str)
    if meds.empty:
        return "<p>Нет данных о приёме препаратов за период.</p>"
    totals = (
        meds.groupby("medicine_name", as_index=False)["doses"]
        .sum()
        .sort_values("doses", ascending=False)
    )
    rows = "".join(
        f"<tr><td>{row.medicine_name}</td><td>{int(row.doses)}</td></tr>"
        for row in totals.itertuples()
    )
    return f"<table><tr><th>Препарат</th><th>Суммарно доз за период</th></tr>{rows}</table>"


def _act_block(user_id: str) -> str:
    history = act_repo.get_act_history(user_id, limit=12)
    if not history:
        return "<p>Тест контроля астмы (ACT) ещё не проходился.</p>"
    rows = "".join(
        f"<tr><td>{h['date'].split(' ')[0]}</td><td>{h['total_score']} / 25</td></tr>"
        for h in history
    )
    return f"<table><tr><th>Дата</th><th>Балл ACT</th></tr>{rows}</table>"


def generate_doctor_report_html(user_id: str, days: int = REPORT_PERIOD_DAYS) -> str:
    analysis_text, analysis_images = analytics_service.run_analysis(user_id, days, None)
    plot_text, plot_images = analytics_service.run_plot(user_id, days, None)

    generated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    charts_html = ""
    for img in plot_images + analysis_images:
        charts_html += f'<img src="{img}" alt="график" />'

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8" />
<title>Отчёт Peak Flow для визита к врачу</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; color: #1E2B2B; max-width: 760px; margin: 32px auto; padding: 0 16px; line-height: 1.5; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  .meta {{ color: #5B6B6B; font-size: 13px; margin-bottom: 24px; }}
  h2 {{ font-size: 16px; margin-top: 28px; border-bottom: 1px solid #E1E9E7; padding-bottom: 6px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #E1E9E7; font-size: 14px; }}
  th {{ color: #5B6B6B; font-weight: 600; width: 45%; }}
  img {{ max-width: 100%; margin-top: 12px; border: 1px solid #E1E9E7; border-radius: 8px; }}
  .disclaimer {{ margin-top: 32px; font-size: 12px; color: #5B6B6B; border-top: 1px solid #E1E9E7; padding-top: 12px; }}
  @media print {{ body {{ margin: 0; }} }}
</style>
</head>
<body>
  <h1>Отчёт Peak Flow для визита к врачу</h1>
  <p class="meta">Сформирован автоматически {generated_at} · период: последние {days} дней</p>

  <h2>Профиль пациента</h2>
  {_profile_block(user_id)}

  <h2>Пороги зон пикфлоу</h2>
  {_zone_block(user_id)}

  <h2>Динамика показаний</h2>
  <p>{plot_text}</p>

  <h2>Статистика и корреляции</h2>
  <p style="white-space: pre-wrap">{analysis_text}</p>
  {charts_html}

  <h2>Приём препаратов за период</h2>
  {_medicine_usage_block(user_id, days)}

  <h2>Тест контроля астмы (ACT)</h2>
  {_act_block(user_id)}

  <p class="disclaimer">
    Отчёт сформирован автоматически приложением Peak Flow на основе данных, введённых
    пользователем самостоятельно, и не заменяет консультацию врача. Тест контроля астмы —
    не официальный лицензированный ACT, а его функциональный аналог с той же шкалой оценки.
  </p>
</body>
</html>"""
