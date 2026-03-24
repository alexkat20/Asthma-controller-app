from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    username: str
    name: str
    surname: str
    birth_date: Optional[datetime] = None


class UserCreate(UserBase):
    pass


class User(UserBase):
    user_id: int

    class Config:
        from_attributes = True


class MedicineBase(BaseModel):
    medicine_name: str
    dose: str


class MedicineCreate(MedicineBase):
    pass


class Medicine(MedicineBase):
    medicine_id: int

    class Config:
        from_attributes = True


class ReadingBase(BaseModel):
    first_try: float
    second_try: float
    third_try: float
    date: datetime


class ReadingCreate(ReadingBase):
    pass


class Reading(ReadingBase):
    id: int
    maximum: float
    green_zone: float
    yellow_zone: float
    red_zone: float

    class Config:
        from_attributes = True


class ExtraInfoBase(BaseModel):
    sport: Optional[bool] = False
    sickness: Optional[bool] = False
    stress: Optional[bool] = False
    allergy: Optional[bool] = False
    date: datetime


class ExtraInfoCreate(ExtraInfoBase):
    pass


class ExtraInfo(ExtraInfoBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True
