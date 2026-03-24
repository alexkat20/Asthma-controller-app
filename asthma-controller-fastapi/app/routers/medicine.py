from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from models import schemas, crud
from models.database import get_db

router = APIRouter()
medicine_tag = "Medicine Management"


@router.post("/medicines/", response_model=schemas.Medicine, tags=[medicine_tag])
def create_medicine(medicine: schemas.MedicineCreate, db: Session = Depends(get_db)):
    return crud.create_medicine(db=db, medicine=medicine)


@router.get("/medicines/", response_model=list[schemas.Medicine], tags=[medicine_tag])
def read_medicines(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    medicines = crud.get_medicines(db=db, skip=skip, limit=limit)
    return medicines


@router.get(
    "/medicines/{medicine_id}", response_model=schemas.Medicine, tags=[medicine_tag]
)
def read_medicine(medicine_id: int, db: Session = Depends(get_db)):
    medicine = crud.get_medicine(db=db, medicine_id=medicine_id)
    if medicine is None:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return medicine


@router.put(
    "/medicines/{medicine_id}", response_model=schemas.Medicine, tags=[medicine_tag]
)
def update_medicine(
    medicine_id: int, medicine: schemas.MedicineCreate, db: Session = Depends(get_db)
):
    updated_medicine = crud.update_medicine(
        db=db, medicine_id=medicine_id, medicine=medicine
    )
    if updated_medicine is None:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return updated_medicine


@router.delete(
    "/medicines/{medicine_id}", response_model=schemas.Medicine, tags=[medicine_tag]
)
def delete_medicine(medicine_id: int, db: Session = Depends(get_db)):
    deleted_medicine = crud.delete_medicine(db=db, medicine_id=medicine_id)
    if deleted_medicine is None:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return deleted_medicine
