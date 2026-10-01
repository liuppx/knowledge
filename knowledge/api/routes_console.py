from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from knowledge.core.settings import get_settings
from knowledge.services.warehouse_scope import warehouse_app_id, warehouse_app_root, warehouse_default_upload_dir

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
web_dist_dir = Path(__file__).resolve().parents[2] / "web" / "dist"
web_index = web_dist_dir / "index.html"
router = APIRouter(include_in_schema=False)
# Registered last in main.py so every API route wins before the SPA catch-all.
spa_router = APIRouter(include_in_schema=False)
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
            "object_storage_endpoint": settings.object_storage_endpoint,
            "object_storage_region": settings.object_storage_region,
            "warehouse_base_url": settings.warehouse_base_url,
            "warehouse_webdav_prefix": settings.warehouse_webdav_prefix,
            "console_asset_version": CONSOLE_ASSET_VERSION,
        },
    )


@spa_router.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
def spa_fallback(path: str, request: Request):
    """Serve the SPA for client-side routes (deep links, refresh).

    API routes are matched first, so only unknown paths land here. Files that
    exist in web/dist (favicon, manifest) are served directly; anything else is
    the SPA shell when the client asks for HTML, and a plain 404 for JSON
    clients so a typo'd API call never receives an HTML page. Non-GET methods
    are claimed too, otherwise unknown POST/DELETE paths would turn into 405.
    """
    if request.method not in ("GET", "HEAD") or not web_index.is_file():
        raise HTTPException(status_code=404, detail="not found")
    if path:
        candidate = (web_dist_dir / path).resolve()
        if candidate.is_file() and web_dist_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
    if "text/html" not in request.headers.get("accept", ""):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(web_index)
