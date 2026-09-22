import pandas as pd
from sqlalchemy import select

from repositories.base_repository import BaseRepository
from repositories.orm_models import ExtraInfo

# Единственное место, где перечислены имена колонок-флагов ExtraInfo — все
# остальные модули (nlp_service, forecast_service, analytics_service,
# export_service, table_service, utils.formatting, logging_service) берут
# список отсюда, а не дублируют его у себя.
TRIGGER_FLAGS = [
    "sport",
    "sickness",
    "stress",
    "allergy",
    "flight",
    "weather",
    "smoke",
    "strong_smells",
    "pets",
    "dust",
    "menstrual_cycle",
]
SYMPTOM_FLAGS = [
    "dyspnea",
    "cough",
    "wheezing",
    "chest_tightness",
    "nocturnal_symptoms",
]
EXTRA_INFO_FLAGS = TRIGGER_FLAGS + SYMPTOM_FLAGS


class ExtraInfoRepository(BaseRepository):
    def add_extra_info(
        self,
        user_id: str,
        date_str: str,
        flags: dict,
        attacks_count: int | None = None,
        record_time: str | None = None,
    ) -> None:
        self.db.add(
            ExtraInfo(
                user_id=user_id,
                date=date_str,
                attacks_count=attacks_count,
                record_time=record_time,
                **{flag: flags.get(flag, False) for flag in EXTRA_INFO_FLAGS},
            )
        )

    def fetch_flags_df(
        self, user_id: str, start_str: str, end_str: str
    ) -> pd.DataFrame:
        columns = [ExtraInfo.date] + [getattr(ExtraInfo, f) for f in EXTRA_INFO_FLAGS]
        stmt = select(*columns).where(
            ExtraInfo.user_id == user_id,
            ExtraInfo.date >= start_str,
            ExtraInfo.date <= end_str,
        )
        return pd.DataFrame(
            self.db.execute(stmt).all(), columns=["date"] + EXTRA_INFO_FLAGS
        )

    def fetch_flags_since_df(self, user_id: str, since_str: str) -> pd.DataFrame:
        columns = [ExtraInfo.date] + [getattr(ExtraInfo, f) for f in EXTRA_INFO_FLAGS]
        stmt = select(*columns).where(
            ExtraInfo.user_id == user_id, ExtraInfo.date >= since_str
        )
        return pd.DataFrame(
            self.db.execute(stmt).all(), columns=["date"] + EXTRA_INFO_FLAGS
        )

    def fetch_extra_info_full_df(
        self, user_id: str, start_str: str, end_str: str
    ) -> pd.DataFrame:
        columns = (
            [ExtraInfo.date]
            + [getattr(ExtraInfo, f) for f in EXTRA_INFO_FLAGS]
            + [ExtraInfo.attacks_count, ExtraInfo.record_time]
        )
        stmt = select(*columns).where(
            ExtraInfo.user_id == user_id,
            ExtraInfo.date >= start_str,
            ExtraInfo.date <= end_str,
        )
        return pd.DataFrame(
            self.db.execute(stmt).all(),
            columns=["date"] + EXTRA_INFO_FLAGS + ["attacks_count", "record_time"],
        )
