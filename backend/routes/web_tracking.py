"""Reverse proxy used to observe API calls made through managed web apps."""

import re
import time
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response


HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}


def init_web_tracking_router(database, config):
    router = APIRouter(prefix="/tracked", tags=["web tracking"])

    @router.api_route(
        "/{app_id}/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def proxy_web_app(app_id: str, path: str, request: Request):
        app = config.get_app_by_id(app_id)
        if not app or app.get("type") != "web" or not app.get("url"):
            raise HTTPException(status_code=404, detail="Tracked web app not found")

        base_url = str(app["url"]).rstrip("/") + "/"
        target_url = urljoin(base_url, path)
        base_parts = urlsplit(base_url)
        target_parts = urlsplit(target_url)
        if target_parts.scheme not in {"http", "https"} or target_parts.netloc != base_parts.netloc:
            raise HTTPException(status_code=400, detail="Invalid tracked app path")
        if request.url.query:
            target_url += "?" + request.url.query

        request_headers = {
            key: value for key, value in request.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS | {"cookie", "authorization"}
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
                upstream = await client.request(
                    request.method,
                    target_url,
                    headers=request_headers,
                    content=await request.body(),
                )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Web app is unavailable: {exc}")

        duration_ms = int((time.perf_counter() - started) * 1000)
        content_type = upstream.headers.get("content-type", "")
        is_api_call = (
            path.lstrip("/").startswith("api/")
            or "application/json" in content_type
            or request.method not in {"GET", "HEAD", "OPTIONS"}
        )
        if is_api_call and database is not None:
            try:
                database.record_usage_event(
                    app_id=app_id,
                    event_name="web_api_called",
                    details={
                        "method": request.method,
                        "route": "/" + path.lstrip("/"),
                        "status_code": upstream.status_code,
                        "duration_ms": duration_ms,
                    },
                    success=upstream.status_code < 400,
                    app_version=app.get("version"),
                    machine_id=config.get_machine_id(),
                    user_alias=config.get_user_alias(),
                )
            except Exception:
                # Tracking must never make the managed app request fail.
                pass

        body = upstream.content
        if "text/html" in content_type:
            body = _rewrite_html(body, app_id, upstream.encoding or "utf-8")

        response_headers = {
            key: value for key, value in upstream.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS | {"content-encoding", "content-security-policy", "set-cookie"}
        }
        location = response_headers.get("location")
        if location:
            response_headers["location"] = _tracked_location(location, base_url, app_id)
        return Response(
            content=body,
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=None,
        )

    return router


def _tracked_location(location: str, base_url: str, app_id: str) -> str:
    absolute = urljoin(base_url, location)
    base = urlsplit(base_url)
    parsed = urlsplit(absolute)
    if parsed.netloc != base.netloc:
        return location
    suffix = parsed.path.lstrip("/")
    if parsed.query:
        suffix += "?" + parsed.query
    return f"/tracked/{app_id}/{suffix}"


def _rewrite_html(body: bytes, app_id: str, encoding: str) -> bytes:
    try:
        html = body.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        html = body.decode("utf-8", errors="replace")
    prefix = f"/tracked/{app_id}/"
    html = re.sub(
        r'''(?i)(\b(?:src|href|action)\s*=\s*["'])/(?!/|tracked/)''',
        lambda match: match.group(1) + prefix,
        html,
    )
    bridge = f'''<script>(function(){{
const p={prefix!r};
const map=u=>typeof u==='string'&&u.startsWith('/')&&!u.startsWith(p)?p+u.slice(1):u;
const f=window.fetch;window.fetch=(u,o)=>f.call(window,map(u),o);
const xo=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(m,u,...a){{return xo.call(this,m,map(u),...a)}};
}})();</script>'''
    if re.search(r"(?i)<head[^>]*>", html):
        html = re.sub(r"(?i)(<head[^>]*>)", r"\1" + bridge, html, count=1)
    else:
        html = bridge + html
    return html.encode("utf-8")
