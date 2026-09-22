from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response

from services.export_service import build_export_workbook

router = APIRouter()

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/api/export/{user_id}")
def get_export(
    user_id: str,
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
):
    custom_range = None
    if start and end:
        try:
            custom_range = (
                datetime.strptime(start, "%Y-%m-%d"),
                datetime.strptime(end, "%Y-%m-%d"),
            )
            days = None
        except ValueError:
            return PlainTextResponse(
                "Некорректный формат дат — используйте YYYY-MM-DD.", status_code=400
            )

    xlsx_bytes, label = build_export_workbook(user_id, days, custom_range)
    if xlsx_bytes is None:
        return PlainTextResponse(f"Нет данных за {label}.", status_code=404)

    filename = f"peakflow_export_{user_id}.xlsx".replace(" ", "_")
    return Response(
        content=xlsx_bytes,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
