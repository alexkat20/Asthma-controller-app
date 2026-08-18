import pandas as pd

from repositories import database as db
from utils.dates import build_date_filter

_FLAG_COLUMNS = ["sport", "sickness", "stress", "allergy", "flight"]
_FLAG_LABELS = {
    "sport": "Sport",
    "sickness": "Sick",
    "stress": "Stress",
    "allergy": "Allergy",
    "flight": "Flight",
}


def build_export_csv(user_id: str, days, custom_range):
    start_str, end_str, label = build_date_filter(days, custom_range)

    conn = db.get_connection()
    readings = db.fetch_full_readings_df(conn, user_id, start_str, end_str)
    meds = db.fetch_medicine_doses_df(conn, user_id, start_str, end_str)
    flags = db.fetch_flags_df(conn, user_id, start_str, end_str)
    conn.close()

    if readings.empty:
        return None, label

    df = readings.rename(
        columns={
            "date": "Date",
            "first_try": "First try",
            "second_try": "Second try",
            "third_try": "Third try",
            "maximum": "Maximum",
            "green_zone": "Green Zone",
            "yellow_zone": "Yellow Zone",
            "red_zone": "Red Zone",
        }
    )

    if not meds.empty:
        pivot = meds.pivot_table(
            index="date",
            columns="medicine_name",
            values="doses",
            aggfunc="sum",
            fill_value=0,
        )
        df = df.merge(pivot, left_on="Date", right_index=True, how="left")
        med_cols = list(pivot.columns)
        df[med_cols] = df[med_cols].fillna(0).astype(int)

    if not flags.empty:

        def _row_extra_info(row) -> str:
            active = [_FLAG_LABELS[col] for col in _FLAG_COLUMNS if row.get(col)]
            return ",".join(active)

        flags = flags.copy()
        flags["Extra info"] = flags.apply(_row_extra_info, axis=1)
        flags_by_date = flags.groupby("date")["Extra info"].agg(
            lambda values: ",".join(sorted(set(",".join(values).split(",")) - {""}))
        )
        df = df.merge(flags_by_date, left_on="Date", right_index=True, how="left")
    else:
        df["Extra info"] = ""
    df["Extra info"] = df["Extra info"].fillna("")
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%m/%d/%Y")

    return df.to_csv(index=False), label
