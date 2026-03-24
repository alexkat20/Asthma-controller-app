from sqlalchemy.orm import Session
from app.models import models
import pandas as pd


def analyze_peak_flow_data(db: Session, user_id: int, period: str):
    period_map = {"week": "7 days", "month": "1 month", "3months": "3 months"}

    query = f"""
        SELECT Maximum, date
        FROM readings
        WHERE user_id=:user_id AND date >= date('now', '-{period_map[period]}') AND Maximum <> 0 AND Maximum IS NOT NULL
        ORDER BY date
    """

    df = pd.read_sql(query, db.bind, params={"user_id": user_id})

    if df.empty:
        return None

    avg = df["Maximum"].mean()
    min_val = df["Maximum"].min()
    max_val = df["Maximum"].max()
    trend = (
        "Improvement"
        if df["Maximum"].iloc[-1] > df["Maximum"].iloc[0]
        else "Deterioration"
    )

    return {"average": avg, "min": min_val, "max": max_val, "trend": trend}
