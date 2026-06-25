import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()
DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "dashboard.html")


@router.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    """Serve o dashboard HTML operacional da Veltrus."""
    return FileResponse(
        path=os.path.abspath(DASHBOARD_PATH),
        media_type="text/html",
    )
