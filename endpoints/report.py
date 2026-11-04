from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from services.report_service import generate_doctor_report_html

router = APIRouter()


@router.get("/api/report/{user_id}", response_class=HTMLResponse)
def get_report(user_id: str):
    return HTMLResponse(content=generate_doctor_report_html(user_id))
