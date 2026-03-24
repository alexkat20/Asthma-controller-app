from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from models import schemas, crud
from models.database import get_db

router = APIRouter()
users_tag = "User Management"


@router.post("/users/", response_model=schemas.User, tags=[users_tag])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    return crud.create_user(db=db, user=user)


@router.get("/users/{user_id}", response_model=schemas.User, tags=[users_tag])
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@router.get("/users/", response_model=list[schemas.User], tags=[users_tag])
def read_users(db: Session = Depends(get_db)):
    db_users = crud.get_users(db)
    return db_users


@router.put("/users/{user_id}", response_model=schemas.User, tags=[users_tag])
def update_user(user_id: int, user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return crud.update_user(db=db, user_id=user_id, user=user)
