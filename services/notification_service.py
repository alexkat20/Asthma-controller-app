from datetime import datetime

from repositories.unit_of_work import UnitOfWork


def push(user_id: str, text: str) -> None:
    with UnitOfWork() as uow:
        uow.notifications.push(
            user_id, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        uow.commit()


def pop_all(user_id: str) -> list:
    with UnitOfWork() as uow:
        messages = uow.notifications.pop_all(user_id)
        uow.commit()
        return messages
