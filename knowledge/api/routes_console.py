from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from knowledge.core.settings import get_settings
from knowledge.services.warehouse_scope import warehouse_app_id, warehouse_app_root, warehouse_default_upload_dir

templates = Jinja2Templates(directory=str(__import__("pathlib").Path(__file__).resolve().parents[1] / "templates"))
web_index = __import__("pathlib").Path(__file__).resolve().parents[2] / "web" / "dist" / "index.html"
router = APIRouter(include_in_schema=False)
settings = get_settings()
CONSOLE_ASSET_VERSION = "20260803-validation-upload-1"


@router.get("/", response_class=HTMLResponse)
def console_home(request: Request):
    if web_index.is_file():
        return FileResponse(web_index)
    return legacy_console_home(request)


@router.get("/legacy-console", response_class=HTMLResponse)
def legacy_console_home(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "warehouse_app_id": warehouse_app_id(),
            "warehouse_app_root": warehouse_app_root(),
            "warehouse_upload_dir": warehouse_default_upload_dir(),
            "warehouse_base_url": settings.warehouse_base_url,
            "warehouse_webdav_prefix": settings.warehouse_webdav_prefix,
            "console_asset_version": CONSOLE_ASSET_VERSION,
        },
    )
