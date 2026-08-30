"""Общий предок для классов-репозиториев.

Репозиторий никогда не создаёт и не закрывает свою сессию сам — её всегда
передаёт `UnitOfWork` (repositories/unit_of_work.py), которому и принадлежит
её жизненный цикл (commit/rollback/close). Поэтому методы репозиториев (кроме
одного документированного исключения в scheduler_lock_repository.py) не
вызывают `self.db.commit()` — иначе часть многотабличной операции могла бы
зафиксироваться в БД раньше, чем провалится следующий её шаг, и обещание
Unit of Work «либо всё, либо ничего» перестало бы выполняться.
"""

from sqlalchemy.orm import Session


class BaseRepository:
    def __init__(self, db: Session):
        self.db = db
