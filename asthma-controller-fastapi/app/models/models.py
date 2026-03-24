from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    name = Column(String)
    surname = Column(String)
    birth_date = Column(DateTime)

    readings = relationship("Reading", back_populates="user")
    extra_info = relationship("ExtraInfo", back_populates="user")
    taken_medicines = relationship("TakenMedicine", back_populates="user")


class Medicine(Base):
    __tablename__ = "medicine"

    medicine_id = Column(Integer, primary_key=True, index=True)
    medicine_name = Column(String)
    dose = Column(String)

    taken_medicines = relationship("TakenMedicine", back_populates="medicine")


class TakenMedicine(Base):
    __tablename__ = "taken_medicine"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicine.medicine_id"))
    user_id = Column(Integer, ForeignKey("users.user_id"))
    doses = Column(Integer)
    date = Column(DateTime)

    medicine = relationship("Medicine", back_populates="taken_medicines")
    user = relationship("User", back_populates="taken_medicines")


class ExtraInfo(Base):
    __tablename__ = "extra_info"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    date = Column(DateTime)
    sport = Column(Boolean, default=False)
    sickness = Column(Boolean, default=False)
    stress = Column(Boolean, default=False)
    allergy = Column(Boolean, default=False)

    user = relationship("User", back_populates="extra_info")


class Reading(Base):
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    date = Column(DateTime)
    first_try = Column(Float)
    second_try = Column(Float)
    third_try = Column(Float)
    maximum = Column(Float)
    green_zone = Column(Float)
    yellow_zone = Column(Float)
    red_zone = Column(Float)

    user = relationship("User", back_populates="readings")
