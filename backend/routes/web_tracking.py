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
ORIGIN_PATH_PREFIX = "__apppilot_origin__/"


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
        base_parts = urlsplit(base_url)
        if path.startswith(ORIGIN_PATH_PREFIX):
            target_url = urljoin(f"{base_parts.scheme}://{base_parts.netloc}/", path[len(ORIGIN_PATH_PREFIX):])
        else:
            target_url = urljoin(base_url, path)
        target_parts = urlsplit(target_url)
        if target_parts.scheme not in {"http", "https"} or target_parts.netloc != base_parts.netloc:
            raise HTTPException(status_code=400, detail="Invalid tracked app path")
        if request.url.query:
            target_url += "?" + request.url.query

        request_headers = {
            key: value for key, value in request.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS | {"cookie", "authorization", "x-apppilot-activity"}
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
            request.headers.get("x-apppilot-activity") in {"fetch", "xhr"}
            or
            path.lstrip("/").startswith("api/")
            or "application/json" in content_type
            or request.method not in {"GET", "HEAD", "OPTIONS"}
        )
        if is_api_call and database is not None:
            activity_path = path[len(ORIGIN_PATH_PREFIX):] if path.startswith(ORIGIN_PATH_PREFIX) else path
            try:
                database.record_usage_event(
                    app_id=app_id,
                    event_name="web_api_called",
                    details={
                        "method": request.method,
                        "route": "/" + activity_path.lstrip("/"),
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
            body = _rewrite_html(body, app_id, upstream.encoding or "utf-8", base_url)

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
    prefix = f"/tracked/{app_id}/"
    raw = urlsplit(location)
    if not raw.scheme and not location.startswith("/"):
        return location

    absolute = urljoin(base_url, location)
    base = urlsplit(base_url)
    parsed = urlsplit(absolute)
    if parsed.netloc != base.netloc:
        return location
    suffix = ORIGIN_PATH_PREFIX + parsed.path.lstrip("/")
    if parsed.query:
        suffix += "?" + parsed.query
    if parsed.fragment:
        suffix += "#" + parsed.fragment
    return prefix + suffix


def _rewrite_html(body: bytes, app_id: str, encoding: str, base_url: str) -> bytes:
    try:
        html = body.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        html = body.decode("utf-8", errors="replace")
    prefix = f"/tracked/{app_id}/"
    origin_prefix = prefix + ORIGIN_PATH_PREFIX
    upstream_origin = f"{urlsplit(base_url).scheme}://{urlsplit(base_url).netloc}"
    html = re.sub(
        r'''(?i)(\b(?:src|href|action)\s*=\s*["'])/(?!/|tracked/)''',
        lambda match: match.group(1) + origin_prefix,
        html,
    )
    html = re.sub(
        rf'''(?i)(\b(?:src|href|action)\s*=\s*["']){re.escape(upstream_origin)}/''',
        lambda match: match.group(1) + origin_prefix,
        html,
    )
    bridge = f'''<script>(function(){{
const p={prefix!r};
const root={origin_prefix!r};
const upstream={upstream_origin!r};
const map=u=>{{
  if(typeof u!=='string')return {{url:u,tracked:false}};
  try{{
    const parsed=new URL(u,location.href);
    if(parsed.origin===upstream)return {{url:root+parsed.pathname.slice(1)+parsed.search+parsed.hash,tracked:true}};
    if(parsed.origin===location.origin){{
      if(parsed.pathname.startsWith(p))return {{url:parsed.pathname+parsed.search+parsed.hash,tracked:true}};
      return {{url:root+parsed.pathname.slice(1)+parsed.search+parsed.hash,tracked:true}};
    }}
  }}catch(_){{}}
  return {{url:u,tracked:false}};
}};
const f=window.fetch;window.fetch=(input,options)=>{{
  const mapped=map(input instanceof Request?input.url:input);
  if(!mapped.tracked)return f.call(window,input,options);
  const headers=new Headers(options&&options.headers||(input instanceof Request?input.headers:undefined));
  headers.set('X-AppPilot-Activity','fetch');
  const next={{...(options||{{}}),headers}};
  return input instanceof Request?f.call(window,new Request(new URL(mapped.url,location.href),input),next):f.call(window,mapped.url,next);
}};
const xo=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(m,u,...a){{const mapped=map(u);this.__appPilotTracked=mapped.tracked;return xo.call(this,m,mapped.url,...a)}};
const xs=XMLHttpRequest.prototype.send;XMLHttpRequest.prototype.send=function(...a){{if(this.__appPilotTracked)this.setRequestHeader('X-AppPilot-Activity','xhr');return xs.apply(this,a)}};
}})();</script>'''
    if re.search(r"(?i)<head[^>]*>", html):
        html = re.sub(r"(?i)(<head[^>]*>)", r"\1" + bridge, html, count=1)
    else:
        html = bridge + html
    return html.encode("utf-8")
