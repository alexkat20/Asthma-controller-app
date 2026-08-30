from datetime import datetime

from sqlalchemy import select

from repositories.base_repository import BaseRepository
from repositories.orm_models import UserProfile


class ProfileRepository(BaseRepository):
    def profile_exists(self, user_id: str) -> bool:
        return self.db.get(UserProfile, user_id) is not None

    def get_profile(self, user_id: str):
        row = self.db.get(UserProfile, user_id)
        if row is None:
            return None
        return {
            "gender": row.gender,
            "age": row.age,
            "height_cm": row.height_cm,
            "weight_kg": row.weight_kg,
            "smoking": row.smoking,
            "allergies": [a for a in (row.allergies or "").split(",") if a],
        }

    def get_created_at(self, user_id: str):
        row = self.db.get(UserProfile, user_id)
        return row.created_at if row else None

    def list_user_ids(self) -> list:
        return list(self.db.execute(select(UserProfile.user_id)).scalars().all())

    def save_profile(self, user_id: str, data: dict) -> None:
        existing = self.db.get(UserProfile, user_id)
        allergies_str = ",".join(data.get("allergies") or [])
        if existing:
            existing.gender = data.get("gender")
            existing.age = data.get("age")
            existing.height_cm = data.get("height_cm")
            existing.weight_kg = data.get("weight_kg")
            existing.smoking = data.get("smoking")
            existing.allergies = allergies_str
        else:
            self.db.add(
                UserProfile(
                    user_id=user_id,
                    gender=data.get("gender"),
                    age=data.get("age"),
                    height_cm=data.get("height_cm"),
                    weight_kg=data.get("weight_kg"),
                    smoking=data.get("smoking"),
                    allergies=allergies_str,
                    created_at=datetime.now().isoformat(),
                )
            )
