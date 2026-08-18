from sqlalchemy.orm import Session

from repositories.orm_models import TreatmentPlan


def get_plan(conn: Session, user_id: str):
    row = conn.get(TreatmentPlan, user_id)
    if row is None:
        return None
    return {
        "baseline_therapy": row.baseline_therapy,
        "worsening_therapy": row.worsening_therapy,
        "attack_therapy": row.attack_therapy,
        "updated_at": row.updated_at,
    }


def save_plan(conn: Session, user_id: str, data: dict, updated_at: str) -> None:
    existing = conn.get(TreatmentPlan, user_id)
    if existing:
        existing.baseline_therapy = data.get("baseline_therapy")
        existing.worsening_therapy = data.get("worsening_therapy")
        existing.attack_therapy = data.get("attack_therapy")
        existing.updated_at = updated_at
    else:
        conn.add(
            TreatmentPlan(
                user_id=user_id,
                baseline_therapy=data.get("baseline_therapy"),
                worsening_therapy=data.get("worsening_therapy"),
                attack_therapy=data.get("attack_therapy"),
                updated_at=updated_at,
            )
        )
    conn.commit()
