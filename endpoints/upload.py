import io

import pandas as pd
from fastapi import APIRouter, File, Form, UploadFile

from repositories.unit_of_work import UnitOfWork

router = APIRouter()

_PERIOD_RU = {"morning": "утренние", "evening": "вечерние"}


def _empty_stats() -> dict:
    return {
        "rows_in_file": 0,
        "readings_inserted": 0,
        "doses_inserted": 0,
        "extra_info_inserted": 0,
        "zone_rows_recalculated": 0,
        "bad_dates_skipped": 0,
    }


def _add_stats(total: dict, part: dict) -> None:
    for key in (
        "rows_in_file",
        "readings_inserted",
        "doses_inserted",
        "extra_info_inserted",
        "bad_dates_skipped",
    ):
        total[key] += part[key]
    total["zone_rows_recalculated"] = part["zone_rows_recalculated"]


def _format_reply(stats: dict, period_note: str) -> str:
    reply = (
        f"✅ Данные загружены{period_note}!\n"
        f"Строк в файле: {stats['rows_in_file']}\n"
        f"Добавлено показаний: {stats['readings_inserted']}\n"
        f"Записей о приёме препаратов: {stats['doses_inserted']}\n"
        f"Записей о состоянии: {stats['extra_info_inserted']}\n"
        f"Зоны пересчитаны для {stats['zone_rows_recalculated']} записей."
    )
    if stats["bad_dates_skipped"]:
        reply += (
            f"\n⚠️ Пропущено строк с некорректной датой: {stats['bad_dates_skipped']}"
        )
    return reply


@router.post("/api/upload")
async def upload(
    user_id: str = Form(...),
    file: UploadFile = File(...),
    period: str = Form("evening"),
):
    if period not in ("morning", "evening"):
        period = "evening"
    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            data = pd.read_csv(io.BytesIO(content))
            with UnitOfWork() as uow:
                stats = uow.readings.import_dataframe(data, user_id, period)
                uow.commit()
            return {
                "reply": _format_reply(stats, f" как {_PERIOD_RU[period]} показания")
            }

        if file.filename.endswith((".xls", ".xlsx")):
            all_sheets = pd.read_excel(io.BytesIO(content), sheet_name=None)
            # Если в книге есть листы, явно названные morning/evening (как в
            # экспорте — см. services/export_service.py), берём период с них,
            # а выбор пользователя ("утро"/"вечер" перед загрузкой файла) для
            # такого файла не нужен
            period_sheets = {
                name.strip().lower(): sheet_df
                for name, sheet_df in all_sheets.items()
                if name.strip().lower() in ("morning", "evening")
            }

            if period_sheets:
                total = _empty_stats()
                with UnitOfWork() as uow:
                    for sheet_period, sheet_df in period_sheets.items():
                        part = uow.readings.import_dataframe(
                            sheet_df, user_id, sheet_period
                        )
                        _add_stats(total, part)
                    uow.commit()
                loaded = " и ".join(
                    _PERIOD_RU[p] for p in ("morning", "evening") if p in period_sheets
                )
                return {"reply": _format_reply(total, f" ({loaded} — по листам файла)")}

            # Обычный однолистовой Excel — период берём из выбора пользователя.
            data = next(iter(all_sheets.values()))
            with UnitOfWork() as uow:
                stats = uow.readings.import_dataframe(data, user_id, period)
                uow.commit()
            return {
                "reply": _format_reply(stats, f" как {_PERIOD_RU[period]} показания")
            }

        return {"reply": "Поддерживаются только файлы CSV и Excel."}
    except Exception as exc:
        return {"reply": f"Ошибка при импорте: {exc}"}
