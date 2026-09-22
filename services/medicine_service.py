from repositories.unit_of_work import UnitOfWork


def add_medicine_from_text(user_id: str, text: str) -> str:
    if ";" in text:
        name, dose = (part.strip() for part in text.split(";", 1))
    else:
        name, dose = text.strip(), ""

    if not name:
        return (
            "Не понял название препарата. Введите название и дозу через точку "
            "с запятой, например: «Симбикорт; 2 дозы»."
        )

    with UnitOfWork() as uow:
        status = uow.medicines.add_medicine(user_id, name, dose)
        uow.commit()

    if status == "exists":
        return (
            f"💊 «{name}» уже есть в вашем списке — добавлять повторно не нужно. "
            "Если хотите изменить дозу, пришлите название и новую дозу через "
            "точку с запятой."
        )
    if status == "dose_updated":
        return f"💊 «{name}» уже был в списке — обновил дозу на «{dose}»."
    return f"💊 Сохранено: {name} ({dose or 'доза не указана'})."
