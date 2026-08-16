"""
ORM-модели — 1:1 соответствие прежней raw-SQL схеме (см. историю database.py).

Осознанное решение: колонки с датой (`date`, `created_at`, `last_sent`, ...)
остаются String в формате "%Y-%m-%d %H:%M:%S", а не SQLAlchemy DateTime.
Это не костыль, а способ радикально сократить объём изменений: весь остальной
код (services/*.py) уже работает с датами как со строками этого формата
(strftime/split/fromisoformat), и формат лексикографически сортируется
(zero-padded ISO-подобный), поэтому сравнения `date >= ? AND date <= ?`
корректно работают И на SQLite, И на PostgreSQL без каких-либо специфичных
для диалекта функций — в отличие от прежнего `datetime('now', ?)`, который
был SQLite-специфичным и на Postgres просто не сработал бы (это и была
главная причина, по которой нельзя было "просто" переключить бэкенд без
переноса на SQLAlchemy).
"""

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from repositories.db_engine import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    surname: Mapped[str | None] = mapped_column(String, nullable=True)
    birth_date: Mapped[str | None] = mapped_column(String, nullable=True)


class Medicine(Base):
    __tablename__ = "medicine"
    __table_args__ = (UniqueConstraint("medicine_name", name="uq_medicine_name"),)

    medicine_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    medicine_name: Mapped[str] = mapped_column(String)
    dose: Mapped[str | None] = mapped_column(String, nullable=True)


class TakenMedicine(Base):
    __tablename__ = "taken_medicine"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicine.medicine_id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    doses: Mapped[int] = mapped_column(Integer)
    date: Mapped[str] = mapped_column(String)


class ExtraInfo(Base):
    __tablename__ = "extra_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    date: Mapped[str] = mapped_column(String)
    sport: Mapped[bool] = mapped_column(Boolean, default=False)
    sickness: Mapped[bool] = mapped_column(Boolean, default=False)
    stress: Mapped[bool] = mapped_column(Boolean, default=False)
    allergy: Mapped[bool] = mapped_column(Boolean, default=False)
    flight: Mapped[bool] = mapped_column(Boolean, default=False)
    # Заполняются только вечерней записью (см. logging_service.py) — по утрам
    # пишутся только показания, extra_info вообще не создаётся.
    attacks_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    record_time: Mapped[str | None] = mapped_column(String, nullable=True)  # "ЧЧ:ММ"


class Reading(Base):
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    date: Mapped[str] = mapped_column(String)
    first_try: Mapped[float] = mapped_column(Float)
    second_try: Mapped[float] = mapped_column(Float)
    third_try: Mapped[float] = mapped_column(Float)
    maximum: Mapped[float] = mapped_column(Float)
    green_zone: Mapped[float | None] = mapped_column(Float, nullable=True)
    yellow_zone: Mapped[float | None] = mapped_column(Float, nullable=True)
    red_zone: Mapped[float | None] = mapped_column(Float, nullable=True)


class UserProfile(Base):
    __tablename__ = "user_profile"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    smoking: Mapped[str | None] = mapped_column(String, nullable=True)
    allergies: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str | None] = mapped_column(String, nullable=True)


class UserLocation(Base):
    __tablename__ = "user_location"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    city_label: Mapped[str | None] = mapped_column(String, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)


class Reminder(Base):
    __tablename__ = "reminders"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_sent: Mapped[str | None] = mapped_column(String, nullable=True)


class ActResult(Base):
    __tablename__ = "act_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String)
    date: Mapped[str] = mapped_column(String)
    answers: Mapped[str] = mapped_column(String)
    total_score: Mapped[int] = mapped_column(Integer)


class ActNotifyState(Base):
    __tablename__ = "act_notify_state"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    last_notified_date: Mapped[str | None] = mapped_column(String, nullable=True)


class FamilyAccess(Base):
    __tablename__ = "family_access"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str | None] = mapped_column(String, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class TreatmentPlan(Base):
    """
    План лечения от врача — по сути цифровой Asthma Action Plan, привязанный
    к уже существующей модели зон: baseline_therapy соответствует зелёной
    зоне (что принимать регулярно), worsening_therapy — жёлтой (что делать
    при ухудшении), attack_therapy — красной/приступу. Одна строка на
    пользователя, как profile/location/reminder_settings.
    """

    __tablename__ = "treatment_plan"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    baseline_therapy: Mapped[str | None] = mapped_column(String, nullable=True)
    worsening_therapy: Mapped[str | None] = mapped_column(String, nullable=True)
    attack_therapy: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[str | None] = mapped_column(String, nullable=True)


class ChatSession(Base):
    """
    Состояние текущего шага диалога (какой шаг мастера записи/анкеты/ACT/плана
    активен, накопленные промежуточные данные) — раньше жило в обычном Python
    dict в памяти процесса (SESSIONS в chat_service.py). Это работало, только
    пока веб-приложение — один процесс: с несколькими воркерами/инстансами
    каждый из них видел только свою половину диалога (подтверждено на практике —
    один и тот же пользователь получал два независимых, рассинхронизированных
    "мозга"). Теперь состояние в БД — неважно, какой воркер обработал запрос.

    data — весь session-dict целиком, сериализованный в JSON. Схема этого
    словаря нестабильна и часто меняется (новые шаги мастеров и т.д.), поэтому
    отдельные колонки под каждый возможный ключ были бы обузой — здесь ровно
    та же экономия, что и в оригинальном in-memory решении: гибкая структура,
    которая нужна только на время одного диалога, а не постоянная схема данных.
    """

    __tablename__ = "chat_sessions"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[str] = mapped_column(String)  # JSON
    updated_at: Mapped[str] = mapped_column(String)


class Notification(Base):
    """
    Очередь уведомлений (напоминания, ежедневный дайджест, просрочен ACT) —
    раньше жила в dict {user_id: [текст, ...]} в памяти процесса
    (_NOTIFICATIONS в notification_service.py), с той же проблемой
    множественных воркеров: push из одного процесса не виден poll-у из
    другого. Одна строка — одно уведомление; pop_all вычитывает и сразу
    удаляет все уведомления пользователя.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


class SchedulerLock(Base):
    """
    Блокировка для фонового планировщика (см. scheduler_worker.py — теперь
    отдельный процесс, не поток внутри веб-воркера). Единственная строка
    (id=1) с арендой (lease): holder — идентификатор процесса, который сейчас
    "владеет" правом выполнять проверки; expires_at — когда аренда истекает.
    Если процесс с планировщиком упал, не освободив лок явно, аренда истечёт
    сама, и следующий тик другого экземпляра (например, при пересечении во
    время деплоя) сможет его перехватить — без ручного вмешательства.
    """

    __tablename__ = "scheduler_lock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    holder: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[str | None] = mapped_column(String, nullable=True)
