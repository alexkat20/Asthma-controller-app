from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from models import schemas, crud
from models.database import get_db

router = APIRouter()
readings_tag = "Peak Flow Readings"


@router.post("/readings/", response_model=schemas.Reading, tags=[readings_tag])
def log_reading(reading: schemas.ReadingCreate, db: Session = Depends(get_db)):
    return crud.create_reading(db=db, reading=reading)


@router.get(
    "/readings/{user_id}", response_model=list[schemas.Reading], tags=[readings_tag]
)
def get_readings(user_id: int, db: Session = Depends(get_db)):
    readings = crud.get_readings_by_user(db=db, user_id=user_id)
    if not readings:
        raise HTTPException(status_code=404, detail="Readings not found")
    return readings


@router.get(
    "/readings/latest/{user_id}", response_model=schemas.Reading, tags=[readings_tag]
)
def get_latest_reading(user_id: int, db: Session = Depends(get_db)):
    reading = crud.get_latest_reading(db=db, user_id=user_id)
    if not reading:
        raise HTTPException(status_code=404, detail="No readings found for this user")
    return reading


@router.delete(
    "/readings/{reading_id}", response_model=schemas.Reading, tags=[readings_tag]
)
def delete_reading(reading_id: int, db: Session = Depends(get_db)):
    reading = crud.delete_reading(db=db, reading_id=reading_id)
    if not reading:
        raise HTTPException(status_code=404, detail="Reading not found")
    return reading
