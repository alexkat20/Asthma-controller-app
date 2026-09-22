import io

import pandas as pd

from repositories.extra_info_repository import EXTRA_INFO_FLAGS
from repositories.unit_of_work import UnitOfWork
from utils.dates import build_date_filter, classify_period

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

_DIFF_COLUMN = "Difference"


def _row_extra_info(row) -> str:
    active = [_FLAG_LABELS[col] for col in _FLAG_COLUMNS if row.get(col)]
    return ",".join(active)


def _build_sheet(
    readings: pd.DataFrame, meds: pd.DataFrame, flags: pd.DataFrame
) -> pd.DataFrame:
    """Общая обвязка одной страницы (переименование колонок, дозы препаратов,
    доп. состояние) — одинаковая что для вечерней, что для утренней."""
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
        flags = flags.copy()
        flags["Extra info"] = flags.apply(_row_extra_info, axis=1)
        flags_by_date = flags.groupby("date")["Extra info"].agg(
            lambda values: ",".join(sorted(set(",".join(values).split(",")) - {""}))
        )
        df = df.merge(flags_by_date, left_on="Date", right_index=True, how="left")
    else:
        df["Extra info"] = ""
    df["Extra info"] = df["Extra info"].fillna("")

    return df


def build_export_workbook(user_id: str, days, custom_range):
    start_str, end_str, label = build_date_filter(days, custom_range)

    with UnitOfWork() as uow:
        readings = uow.readings.fetch_full_readings_df(user_id, start_str, end_str)
        meds = uow.medicines.fetch_medicine_doses_df(user_id, start_str, end_str)
        flags = uow.extra_info.fetch_flags_df(user_id, start_str, end_str)

    if readings.empty:
        return None, label

    readings = readings.copy()
    readings["_period"] = pd.to_datetime(readings["date"]).map(classify_period)

    sheets: dict[str, pd.DataFrame] = {}
    for period in ("evening", "morning"):
        period_readings = readings[readings["_period"] == period].drop(
            columns=["_period"]
        )
        if period_readings.empty:
            continue
        dates_in_period = set(period_readings["date"])
        period_meds = (
            meds[meds["date"].isin(dates_in_period)] if not meds.empty else meds
        )
        period_flags = (
            flags[flags["date"].isin(dates_in_period)] if not flags.empty else flags
        )
        df = _build_sheet(period_readings, period_meds, period_flags)
        df["Date"] = pd.to_datetime(df["Date"])
        sheets[period] = df

    if not sheets:
        return None, label

    if "morning" in sheets:
        morning = sheets["morning"].copy()
        morning["_day"] = morning["Date"].dt.normalize()
        if "evening" in sheets:
            evening_avg_by_day = (
                sheets["evening"]
                .assign(_day=sheets["evening"]["Date"].dt.normalize())
                .groupby("_day")["Maximum"]
                .mean()
                .rename("_evening_avg")
            )
            morning = morning.merge(
                evening_avg_by_day, left_on="_day", right_index=True, how="left"
            )
            diff = morning["Maximum"] - morning["_evening_avg"]
            morning[_DIFF_COLUMN] = diff.where(morning["Maximum"] != 0)
            morning.drop(columns=["_evening_avg"], inplace=True)
        else:
            morning[_DIFF_COLUMN] = pd.NA
        sheets["morning"] = morning.drop(columns=["_day"])

    for df in sheets.values():
        df["Date"] = df["Date"].dt.strftime("%m/%d/%Y")

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for period in ("evening", "morning"):
            if period in sheets:
                sheets[period].to_excel(writer, sheet_name=period, index=False)
    buffer.seek(0)
    return buffer.getvalue(), label
