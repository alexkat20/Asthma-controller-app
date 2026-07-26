"""
Peak Flow — веб-чат-бот (без Telegram).

Вся бизнес-логика (БД/зоны — db.py, NLP — nlp.py, прогноз — forecast.py) не зависит
от Telegram и переиспользуется как есть. Этот файл — новый "фронт контроллер":
принимает сообщения через HTTP/JSON вместо Telegram Update и отвечает в том же
формате, что легко рендерится любым чат-интерфейсом (см. static/).

Запуск: uvicorn app:app --reload --port 8000
Открыть: http://localhost:8000
"""

import base64
import io
import re
import threading
import time as time_module
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # без дисплея — рендерим сразу в файл/буфер
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import nlp
import forecast

app = FastAPI(title="Peak Flow Chat Bot")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

db.init_db()

# ---------------------------------------------------------------------------
# Состояние диалога и очередь фоновых уведомлений — в памяти процесса.
# Для одного/нескольких пользователей личного трекера этого достаточно;
# при желании несложно перенести SESSIONS в саму БД (таблица sessions).
# ---------------------------------------------------------------------------
SESSIONS: dict = {}
NOTIFICATIONS: dict = {}
_notif_lock = threading.Lock()


def get_session(user_id: str) -> dict:
    return SESSIONS.setdefault(
        user_id, {"awaiting_period": None, "awaiting_medicine_name": False}
    )


def push_notification(user_id: str, text: str) -> None:
    with _notif_lock:
        NOTIFICATIONS.setdefault(user_id, []).append(text)


PERIOD_DAYS = {
    "неделя": 7,
    "неделю": 7,
    "week": 7,
    "2 недели": 14,
    "2недели": 14,
    "две недели": 14,
    "месяц": 30,
    "month": 30,
    "квартал": 90,
    "3 месяца": 90,
    "quarter": 90,
    "год": 365,
    "year": 365,
}
QUICK_PERIODS = ["Неделя", "2 недели", "Месяц", "Квартал", "Год"]
MAIN_MENU = [
    "📊 Анализ",
    "📈 График",
    "🔮 Прогноз",
    "💊 Добавить лекарство",
    "⏰ Напоминание",
]

ZONE_RU = {
    "green": "🟢 зелёная",
    "yellow": "🟡 жёлтая",
    "red": "🔴 красная",
    "unknown": "нет данных",
}
FLAG_RU = {
    "sport": "спорт",
    "sickness": "болезнь",
    "stress": "стресс",
    "allergy": "аллергия",
    "flight": "перелёт",
}

CUSTOM_RANGE_RE = re.compile(
    r"(\d{1,2}\.\d{1,2}\.\d{4})\s*[-–—]\s*(\d{1,2}\.\d{1,2}\.\d{4})"
)


class ChatIn(BaseModel):
    user_id: str
    text: str


class ChatOut(BaseModel):
    reply: str
    quick_replies: list = []
    images: list = []


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def fig_to_data_uri() -> str:
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close()
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode()


def parse_period(text: str):
    """Возвращает (days, None) для именованного периода или (None, (start, end)) для диапазона дат."""
    t = text.strip().lower()
    if t in PERIOD_DAYS:
        return PERIOD_DAYS[t], None
    m = CUSTOM_RANGE_RE.search(t)
    if m:
        try:
            start = datetime.strptime(m.group(1), "%d.%m.%Y")
            end = datetime.strptime(m.group(2), "%d.%m.%Y")
            return None, (start, end)
        except ValueError:
            return None, None
    return None, None


def _date_filter(days, custom_range):
    if custom_range:
        start, end = custom_range
        return (
            "date >= ? AND date <= ?",
            (start.strftime("%Y-%m-%d 00:00:00"), end.strftime("%Y-%m-%d 23:59:59")),
            f"{start.date().strftime('%d.%m.%Y')}—{end.date().strftime('%d.%m.%Y')}",
        )
    return (
        "date >= datetime('now', ?)",
        (f"-{days} days",),
        {7: "неделю", 14: "2 недели", 30: "месяц", 90: "квартал", 365: "год"}.get(
            days, f"{days} дн."
        ),
    )


# ---------------------------------------------------------------------------
# Анализ, график, прогноз, умная запись
# ---------------------------------------------------------------------------
def run_analysis(user_id: str, days, custom_range) -> tuple:
    where, extra_params, label = _date_filter(days, custom_range)
    conn = db.get_connection()
    df = pd.read_sql(
        f"SELECT date, maximum FROM readings WHERE user_id=? AND {where} AND maximum IS NOT NULL ORDER BY date",
        conn,
        params=(user_id, *extra_params),
    )
    if df.empty:
        conn.close()
        return f"Нет данных за {label}.", []

    df["date"] = pd.to_datetime(df["date"])
    df["day_key"] = df["date"].dt.normalize()
    daily = df.groupby("day_key", as_index=False)["maximum"].mean()

    flags = pd.read_sql(
        f"SELECT date, sport, sickness, stress, allergy, flight FROM extra_info WHERE user_id=? AND {where}",
        conn,
        params=(user_id, *extra_params),
    )
    meds = pd.read_sql(
        f"""
        SELECT tm.date, m.medicine_name, tm.doses FROM taken_medicine tm
        JOIN medicine m ON m.medicine_id = tm.medicine_id
        WHERE tm.user_id=? AND {re.sub(r'(?<![a-z])date(?![a-z])', 'tm.date', where)}
        """,
        conn,
        params=(user_id, *extra_params),
    )
    conn.close()

    merged = daily.copy()
    flag_cols = ["sport", "sickness", "stress", "allergy", "flight"]
    if not flags.empty:
        flags["day_key"] = pd.to_datetime(flags["date"]).dt.normalize()
        flags_agg = flags.groupby("day_key", as_index=False)[flag_cols].max()
        merged = merged.merge(flags_agg, on="day_key", how="left")
    for col in flag_cols:
        if col not in merged.columns:
            merged[col] = 0
    merged[flag_cols] = merged[flag_cols].fillna(0)

    med_cols = []
    if not meds.empty:
        meds["day_key"] = pd.to_datetime(meds["date"]).dt.normalize()
        pivot = meds.pivot_table(
            index="day_key",
            columns="medicine_name",
            values="doses",
            aggfunc="sum",
            fill_value=0,
        )
        pivot = pivot.reset_index()
        merged = merged.merge(pivot, on="day_key", how="left")
        med_cols = [c for c in pivot.columns if c != "day_key"]
        merged[med_cols] = merged[med_cols].fillna(0)

    merged["weekday"] = merged["day_key"].dt.day_name()
    weekday_dummies = pd.get_dummies(merged["weekday"], prefix="день")

    corr_input = pd.concat(
        [merged[["maximum"] + flag_cols + med_cols], weekday_dummies], axis=1
    )
    corr_matrix = (
        corr_input.corr(numeric_only=True)[["maximum"]].drop(index="maximum").dropna()
    )

    avg, mn, mx = df["maximum"].mean(), df["maximum"].min(), df["maximum"].max()
    trend = (
        "рост"
        if df["maximum"].iloc[-1] > df["maximum"].iloc[0]
        else "снижение"
        if df["maximum"].iloc[-1] < df["maximum"].iloc[0]
        else "стабильно"
    )

    images = []
    top_factors = ""
    if not corr_matrix.empty:
        plt.figure(figsize=(5, max(2.5, 0.32 * len(corr_matrix))))
        sns.heatmap(
            corr_matrix, annot=True, cmap="coolwarm", center=0, fmt=".2f", cbar=False
        )
        plt.title("Корреляция с максимумом пикфлоу")
        plt.tight_layout()
        images.append(fig_to_data_uri())
        top = corr_matrix["maximum"].abs().sort_values(ascending=False).head(3)
        top_factors = "\nСильнее всего связаны с максимумом: " + ", ".join(top.index)

    text = (
        f"📊 Анализ за {label}\n"
        f"Среднее: {avg:.0f}, минимум: {mn:.0f}, максимум: {mx:.0f}\n"
        f"Тренд за период: {trend}"
        f"{top_factors}"
    )
    return text, images


def run_plot(user_id: str, days, custom_range) -> tuple:
    where, extra_params, label = _date_filter(days, custom_range)
    conn = db.get_connection()
    df = pd.read_sql(
        f"SELECT date, maximum FROM readings WHERE user_id=? AND {where} AND maximum IS NOT NULL ORDER BY date",
        conn,
        params=(user_id, *extra_params),
    )
    thresholds = db.calculate_zone_thresholds(conn, user_id, datetime.now())
    conn.close()

    if df.empty:
        return f"Нет данных за {label}.", []

    df["date"] = pd.to_datetime(df["date"])

    plt.figure(figsize=(8, 4))
    if thresholds:
        top = max(df["maximum"].max(), thresholds.green_zone) * 1.05
        plt.axhspan(thresholds.green_zone, top, color="#2F9E44", alpha=0.08)
        plt.axhspan(
            thresholds.yellow_zone, thresholds.green_zone, color="#E8A33D", alpha=0.12
        )
        plt.axhspan(0, thresholds.yellow_zone, color="#D14343", alpha=0.08)
    plt.plot(df["date"], df["maximum"], marker="o", color="#3E6FB0", label="показания")
    if len(df) >= 5:
        df["trend"] = df["maximum"].rolling(5, min_periods=1).mean()
        plt.plot(
            df["date"],
            df["trend"],
            linestyle="--",
            color="#444",
            label="тренд (скольз. среднее)",
        )
    plt.title(f"Динамика пикфлоу — {label}")
    plt.xlabel("Дата")
    plt.ylabel("Пикфлоу")
    plt.grid(alpha=0.3)
    plt.xticks(rotation=40)
    plt.legend()
    image = fig_to_data_uri()

    return f"📈 График за {label}.", [image]


def run_predict(user_id: str) -> tuple:
    conn = db.get_connection()
    today = forecast.forecast_today(conn, user_id)
    week = forecast.forecast_week(conn, user_id)
    conn.close()

    if today is None:
        return (
            "Недостаточно данных для прогноза — сначала запишите несколько показаний.",
            [],
        )

    lines = [
        f"🔮 Прогноз на сегодня ({today['date'].strftime('%d.%m')}): ~{today['predicted_value']:.0f}, "
        f"зона: {ZONE_RU[today['zone']]}"
    ]
    if today["active_flags_used"]:
        lines.append(
            "Учтено вчерашнее состояние: "
            + ", ".join(FLAG_RU[f] for f in today["active_flags_used"])
        )
    slope = today["trend_slope_per_day"]
    if abs(slope) >= 0.5:
        direction = "рост" if slope > 0 else "снижение"
        lines.append(
            f"Тренд последних недель: {direction} ~{abs(slope):.1f} л/мин в день."
        )

    plt.figure(figsize=(7, 3.3))
    dates = [d["date"] for d in week]
    values = [d["predicted_value"] for d in week]
    colors = {
        "green": "#2F9E44",
        "yellow": "#E8A33D",
        "red": "#D14343",
        "unknown": "#999",
    }
    plt.plot(dates, values, color="#3E6FB0", zorder=1)
    plt.scatter(dates, values, c=[colors[d["zone"]] for d in week], zorder=2, s=60)
    plt.title("Прогноз на ближайшую неделю")
    plt.ylabel("Пикфлоу")
    plt.grid(alpha=0.3)
    plt.xticks(rotation=30)
    image = fig_to_data_uri()

    lines.append(
        "\n📅 На неделю вперёд (без учёта будущих факторов, кроме сегодняшнего):"
    )
    for d in week:
        lines.append(
            f"  {d['date'].strftime('%d.%m')}: ~{d['predicted_value']:.0f} ({ZONE_RU[d['zone']]})"
        )

    return "\n".join(lines), [image]


def run_smart_log(user_id: str, text: str):
    """Возвращает готовый текст ответа, либо None, если в сообщении не нашлось показаний
    (значит, это не попытка записи, а что-то другое — вызывающий код покажет справку)."""
    conn = db.get_connection()
    db.ensure_user(conn, user_id)
    known_medicines = [
        r[0] for r in conn.execute("SELECT medicine_name FROM medicine").fetchall()
    ]
    parsed = nlp.parse_log_message(text, known_medicines)

    if not parsed["peak_flow"]:
        conn.close()
        return None

    values = parsed["peak_flow"][:3]
    while len(values) < 3:
        values.append(values[-1])

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M:%S")
    _, thresholds, zone = db.insert_reading(conn, user_id, now, *values)
    maximum = max(values)

    for med in parsed["medicines"]:
        medicine_id = db.get_or_create_medicine_id(conn, med["name"])
        conn.execute(
            "INSERT INTO taken_medicine (medicine_id, user_id, doses, date) VALUES (?, ?, ?, ?)",
            (medicine_id, user_id, med["dose"], date_str),
        )

    flags = parsed["flags"]
    if any(flags.values()):
        conn.execute(
            """
            INSERT INTO extra_info (user_id, date, sport, sickness, stress, allergy, flight)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                date_str,
                flags["sport"],
                flags["sickness"],
                flags["stress"],
                flags["allergy"],
                flags["flight"],
            ),
        )
    conn.commit()
    conn.close()

    zone_messages = {
        "green": f"✅ Пикфлоу {maximum:.0f} — {ZONE_RU['green']} зона (≥{thresholds.green_zone:.0f}). Стабильно.",
        "yellow": f"⚠️ Пикфлоу {maximum:.0f} — {ZONE_RU['yellow']} зона ({thresholds.yellow_zone:.0f}–{thresholds.green_zone:.0f}). Стоит понаблюдать за собой.",
        "red": f"🚨 Пикфлоу {maximum:.0f} — {ZONE_RU['red']} зона (<{thresholds.yellow_zone:.0f}). Рекомендуется консультация врача.",
    }
    med_str = (
        ", ".join(f"{m['name']} × {m['dose']}" for m in parsed["medicines"])
        or "не указано"
    )
    flags_str = ", ".join(FLAG_RU[f] for f, v in flags.items() if v) or "не указано"

    return (
        f"{zone_messages.get(zone, f'Сохранено: максимум {maximum:.0f}')}\n\n"
        f"Показания: {', '.join(str(int(v)) for v in values)}\n"
        f"Препараты: {med_str}\n"
        f"Состояние: {flags_str}"
    )


def add_medicine_from_text(text: str) -> str:
    if ";" in text:
        name, dose = (part.strip() for part in text.split(";", 1))
    else:
        name, dose = text.strip(), ""
    conn = db.get_connection()
    conn.execute(
        """
        INSERT INTO medicine (medicine_name, dose) VALUES (?, ?)
        ON CONFLICT(medicine_name) DO UPDATE SET dose = excluded.dose
        """,
        (name, dose),
    )
    conn.commit()
    conn.close()
    return f"💊 Сохранено: {name} ({dose or 'доза не указана'})."


def handle_reminder_command(user_id: str, text: str) -> str:
    conn = db.get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            user_id TEXT PRIMARY KEY, hour INTEGER, minute INTEGER, last_sent TEXT
        )
        """
    )
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        conn.execute(
            """
            INSERT INTO reminders (user_id, hour, minute, last_sent) VALUES (?, ?, ?, NULL)
            ON CONFLICT(user_id) DO UPDATE SET hour = excluded.hour, minute = excluded.minute
            """,
            (user_id, hour, minute),
        )
        conn.commit()
        conn.close()
        return f"⏰ Ежедневное напоминание установлено на {hour:02d}:{minute:02d}."

    row = conn.execute(
        "SELECT hour, minute FROM reminders WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    if row:
        return f"⏰ Сейчас напоминание установлено на {row[0]:02d}:{row[1]:02d}. Чтобы изменить — напишите, например, «напоминание 08:30»."
    return "У вас ещё нет напоминания. Установите его, например: «напоминание 09:00»."


def welcome_text() -> str:
    return (
        "Привет! Я слежу за вашей пикфлоуметрией.\n\n"
        "Просто пришлите показания одним сообщением — я сам разберу цифры, препараты "
        "и самочувствие:\n"
        "«450 460 470 сальбутамол 2 дозы, занимался спортом»\n\n"
        "Также доступны: анализ, график, прогноз, добавление лекарств, напоминания "
        "и загрузка истории файлом (кнопка ⬆ вверху)."
    )


def help_text() -> str:
    return (
        "Не совсем понял сообщение. Что я умею:\n"
        "• Запись показаний одним сообщением: «450 460 470 спорт»\n"
        "• «анализ» — статистика и корреляции за период\n"
        "• «график» — динамика пикфлоу\n"
        "• «прогноз» — ожидания на сегодня и неделю\n"
        "• «добавить лекарство» — сохранить препарат и дозу\n"
        "• «напоминание 09:00» — ежедневное напоминание\n"
        "• загрузка CSV/Excel — кнопка ⬆ вверху экрана"
    )


# ---------------------------------------------------------------------------
# Маршрутизация сообщений
# ---------------------------------------------------------------------------
GREETINGS = {
    "начать",
    "старт",
    "/start",
    "привет",
    "меню",
    "хай",
    "hello",
    "hi",
    "start",
}
HELP_WORDS = {"помощь", "команды", "help", "?"}


def process_message(user_id: str, text: str) -> ChatOut:
    session = get_session(user_id)
    t = text.strip()
    tl = t.lower()

    if tl in GREETINGS:
        session["awaiting_period"] = None
        session["awaiting_medicine_name"] = False
        return ChatOut(reply=welcome_text(), quick_replies=MAIN_MENU)

    if tl in HELP_WORDS:
        return ChatOut(reply=help_text(), quick_replies=MAIN_MENU)

    if session.get("awaiting_medicine_name"):
        session["awaiting_medicine_name"] = False
        return ChatOut(reply=add_medicine_from_text(t), quick_replies=MAIN_MENU)

    if session.get("awaiting_period"):
        days, custom = parse_period(t)
        if days is None and custom is None:
            return ChatOut(
                reply="Не понял период. Выберите один из вариантов ниже или пришлите диапазон ДД.ММ.ГГГГ-ДД.ММ.ГГГГ.",
                quick_replies=QUICK_PERIODS,
            )
        kind = session["awaiting_period"]
        session["awaiting_period"] = None
        if kind == "analysis":
            reply, images = run_analysis(user_id, days, custom)
        else:
            reply, images = run_plot(user_id, days, custom)
        return ChatOut(reply=reply, images=images, quick_replies=MAIN_MENU)

    if "анализ" in tl:
        session["awaiting_period"] = "analysis"
        return ChatOut(
            reply="За какой период построить анализ?", quick_replies=QUICK_PERIODS
        )

    if "график" in tl:
        session["awaiting_period"] = "plot"
        return ChatOut(
            reply="За какой период построить график?", quick_replies=QUICK_PERIODS
        )

    if "прогноз" in tl:
        reply, images = run_predict(user_id)
        return ChatOut(reply=reply, images=images, quick_replies=MAIN_MENU)

    if "напомин" in tl:
        return ChatOut(
            reply=handle_reminder_command(user_id, t), quick_replies=MAIN_MENU
        )

    if "лекарств" in tl or "препарат" in tl:
        session["awaiting_medicine_name"] = True
        return ChatOut(
            reply="Введите название и дозу через точку с запятой, например: «Симбикорт; 2 дозы»."
        )

    # иначе пробуем разобрать как запись показаний
    reply = run_smart_log(user_id, t)
    if reply is not None:
        return ChatOut(reply=reply, quick_replies=MAIN_MENU)

    return ChatOut(reply=help_text(), quick_replies=MAIN_MENU)


# ---------------------------------------------------------------------------
# Фоновый планировщик: ежедневные напоминания/прогноз (без Telegram push —
# кладём сообщение в очередь, а фронтенд забирает его поллингом).
# ---------------------------------------------------------------------------
def _send_daily_digest(conn, user_id: str) -> None:
    today = forecast.forecast_today(conn, user_id)
    if today is None:
        msg = "📢 Не забудьте записать сегодняшние показания пикфлоуметра!"
    else:
        msg = (
            f"📢 Доброе утро! Ожидаемый пикфлоу сегодня: ~{today['predicted_value']:.0f} "
            f"({ZONE_RU[today['zone']]}). Сделайте замер и сравните с прогнозом."
        )
    push_notification(user_id, msg)


def _check_reminders() -> None:
    conn = db.get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            user_id TEXT PRIMARY KEY, hour INTEGER, minute INTEGER, last_sent TEXT
        )
        """
    )
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT user_id, hour, minute, last_sent FROM reminders"
    ).fetchall()
    for user_id, hour, minute, last_sent in rows:
        if now.hour == hour and now.minute == minute and last_sent != today_str:
            _send_daily_digest(conn, user_id)
            conn.execute(
                "UPDATE reminders SET last_sent=? WHERE user_id=?", (today_str, user_id)
            )
    conn.commit()
    conn.close()


def _scheduler_loop() -> None:
    while True:
        try:
            _check_reminders()
        except Exception as exc:  # фоновый поток не должен падать целиком из-за одной ошибки
            print(f"[scheduler] ошибка: {exc}")
        time_module.sleep(60)


@app.on_event("startup")
def start_scheduler() -> None:
    threading.Thread(target=_scheduler_loop, daemon=True).start()


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatOut)
def chat(payload: ChatIn) -> ChatOut:
    return process_message(payload.user_id, payload.text)


@app.post("/api/upload")
async def upload(user_id: str = Form(...), file: UploadFile = File(...)):
    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            data = pd.read_csv(io.BytesIO(content))
        elif file.filename.endswith((".xls", ".xlsx")):
            data = pd.read_excel(io.BytesIO(content))
        else:
            return {"reply": "Поддерживаются только файлы CSV и Excel."}

        conn = db.get_connection()
        db.ensure_user(conn, user_id)
        stats = db.import_dataframe(conn, data, user_id)
        conn.close()

        reply = (
            "✅ Данные загружены!\n"
            f"Строк в файле: {stats['rows_in_file']}\n"
            f"Добавлено показаний: {stats['readings_inserted']}\n"
            f"Записей о приёме препаратов: {stats['doses_inserted']}\n"
            f"Записей о состоянии: {stats['extra_info_inserted']}\n"
            f"Зоны пересчитаны для {stats['zone_rows_recalculated']} записей."
        )
        if stats["bad_dates_skipped"]:
            reply += f"\n⚠️ Пропущено строк с некорректной датой: {stats['bad_dates_skipped']}"
        return {"reply": reply}
    except Exception as exc:
        return {"reply": f"Ошибка при импорте: {exc}"}


@app.get("/api/notifications/{user_id}")
def get_notifications(user_id: str):
    with _notif_lock:
        messages = NOTIFICATIONS.pop(user_id, [])
    return {"messages": messages}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
