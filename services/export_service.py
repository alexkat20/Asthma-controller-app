import pandas as pd

from repositories.extra_info_repository import EXTRA_INFO_FLAGS
from repositories.unit_of_work import UnitOfWork
from utils.dates import build_date_filter

_FLAG_COLUMNS = EXTRA_INFO_FLAGS
_FLAG_LABELS = {
    "sport": "Sport",
    "sickness": "Sick",
    "stress": "Stress",
    "allergy": "Allergy",
    "flight": "Flight",
    "weather": "Weather",
    "smoke": "Smoke",
    "strong_smells": "Strong smells",
    "pets": "Pets",
    "dust": "Dust",
    "menstrual_cycle": "Menstrual cycle",
    "dyspnea": "Dyspnea",
    "cough": "Cough",
    "wheezing": "Wheezing",
    "chest_tightness": "Chest tightness",
    "nocturnal_symptoms": "Nocturnal symptoms",
}


def build_export_csv(user_id: str, days, custom_range):
    start_str, end_str, label = build_date_filter(days, custom_range)

    with UnitOfWork() as uow:
        readings = uow.readings.fetch_full_readings_df(user_id, start_str, end_str)
        meds = uow.medicines.fetch_medicine_doses_df(user_id, start_str, end_str)
        flags = uow.extra_info.fetch_flags_df(user_id, start_str, end_str)

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
