from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

web_dist_dir = Path(__file__).resolve().parents[2] / "web" / "dist"
web_index = web_dist_dir / "index.html"
router = APIRouter(include_in_schema=False)
# Registered last in main.py so every API route wins before the SPA catch-all.
spa_router = APIRouter(include_in_schema=False)

MISSING_BUILD_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Knowledge</title></head>
<body style="font-family:system-ui,sans-serif;max-width:640px;margin:10vh auto;line-height:1.6;padding:0 16px">
<h1>Knowledge API 正在运行</h1>
<p>前端尚未构建。在仓库中执行 <code>cd web &amp;&amp; npm ci &amp;&amp; npm run build</code> 生成 <code>web/dist</code> 后刷新本页。</p>
<p>接口文档：<a href="/docs">/docs</a> · 健康检查：<a href="/health">/health</a></p>
</body></html>
"""


@router.get("/", response_class=HTMLResponse)
def console_home():
    if web_index.is_file():
        return FileResponse(web_index)
    return HTMLResponse(MISSING_BUILD_HTML)


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
