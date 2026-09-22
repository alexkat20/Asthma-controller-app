"""Unit of Work — одна SQLAlchemy-сессия на бизнес-операцию.

Все репозитории внутри `with UnitOfWork() as uow:` разделяют одну и ту же
сессию (`uow.db`). Ни один метод репозитория (кроме документированного
исключения в scheduler_lock_repository.py) не коммитит сам — коммит
происходит только на границе UnitOfWork (при выходе из `with` без
исключения, либо явным `uow.commit()`), поэтому запись в несколько таблиц за
одну операцию фиксируется целиком или не фиксируется вообще:

    with UnitOfWork() as uow:
        uow.users.ensure_user(user_id)
        uow.readings.insert_reading(user_id, ...)
        uow.medicines.add_taken_medicine(...)
        uow.commit()

Если исключение вылетит до uow.commit(), __exit__ откатит всё через
db.rollback() — commit() вызывать вручную не обязательно, но явный вызов в
конце операции делает намерение читаемым.

Для одиночного чтения синтаксис тот же — сессия всё равно нужна:

    with UnitOfWork() as uow:
        return uow.profiles.get_profile(user_id)
"""

from repositories.act_repository import ActRepository
from repositories.db_engine import get_session
from repositories.extra_info_repository import ExtraInfoRepository
from repositories.family_repository import FamilyRepository
from repositories.medicine_repository import MedicineRepository
from repositories.notification_repository import NotificationRepository
from repositories.profile_repository import ProfileRepository
from repositories.reading_repository import ReadingRepository
from repositories.scheduler_lock_repository import SchedulerLockRepository
from repositories.session_repository import SessionRepository
from repositories.settings_repository import SettingsRepository
from repositories.treatment_plan_repository import TreatmentPlanRepository
from repositories.user_repository import UserRepository


class UnitOfWork:
    def __enter__(self) -> "UnitOfWork":
        self.db = get_session()
        self.act = ActRepository(self.db)
        self.extra_info = ExtraInfoRepository(self.db)
        self.family = FamilyRepository(self.db)
        self.medicines = MedicineRepository(self.db)
        self.notifications = NotificationRepository(self.db)
        self.profiles = ProfileRepository(self.db)
        self.readings = ReadingRepository(self.db)
        self.scheduler_lock = SchedulerLockRepository(self.db)
        self.chat_sessions = SessionRepository(self.db)
        self.settings = SettingsRepository(self.db)
        self.treatment_plans = TreatmentPlanRepository(self.db)
        self.users = UserRepository(self.db)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.db.commit()
            else:
                self.db.rollback()
        finally:
            self.db.close()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
