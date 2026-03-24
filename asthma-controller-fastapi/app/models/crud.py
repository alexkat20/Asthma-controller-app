from sqlalchemy.orm import Session
from . import models, schemas


def create_user(db: Session, user: schemas.UserCreate):
    db_user = models.User(**user.dict())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user(db: Session, user_id: int, user: schemas.UserCreate):
    db_user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if db_user:
        for key, value in user.dict(exclude_unset=True).items():
            setattr(db_user, key, value)
        db.commit()
        db.refresh(db_user)
    return db_user


def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.user_id == user_id).first()


def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()


def get_users(db: Session):
    return db.query(models.User).all()


def get_users(db: Session, skip: int = 0, limit: int = 10):
    return db.query(models.User).offset(skip).limit(limit).all()


def create_reading(db: Session, reading: schemas.ReadingCreate):
    db_reading = models.Reading(**reading.dict())
    db.add(db_reading)
    db.commit()
    db.refresh(db_reading)
    return db_reading


def get_reading(db: Session, reading_id: int):
    return db.query(models.Reading).filter(models.Reading.id == reading_id).first()


def get_readings(db: Session, user_id: int, skip: int = 0, limit: int = 10):
    return (
        db.query(models.Reading)
        .filter(models.Reading.user_id == user_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_medicine(db: Session, medicine: schemas.MedicineCreate):
    db_medicine = models.Medicine(**medicine.dict())
    db.add(db_medicine)
    db.commit()
    db.refresh(db_medicine)
    return db_medicine


def get_medicine(db: Session, medicine_id: int):
    return db.query(models.Medicine).filter(models.Medicine.id == medicine_id).first()


def get_medicines(db: Session, skip: int = 0, limit: int = 10):
    return db.query(models.Medicine).offset(skip).limit(limit).all()


def update_medicine(db: Session, medicine_id: int, medicine: schemas.MedicineCreate):
    db_medicine = (
        db.query(models.Medicine).filter(models.Medicine.id == medicine_id).first()
    )
    if db_medicine:
        for key, value in medicine.dict(exclude_unset=True).items():
            setattr(db_medicine, key, value)
        db.commit()
        db.refresh(db_medicine)
    return db_medicine


def delete_medicine(db: Session, medicine_id: int):
    db_medicine = (
        db.query(models.Medicine).filter(models.Medicine.id == medicine_id).first()
    )
    if db_medicine:
        db.delete(db_medicine)
        db.commit()
    return db_medicine
