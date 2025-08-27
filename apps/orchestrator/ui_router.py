from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

router = APIRouter()

@router.get("/ui", response_class=HTMLResponse)
def ui():
    html_path = Path(__file__).with_name("ui.html")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))
