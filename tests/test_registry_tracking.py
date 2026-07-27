import json
import os
import re
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from backend.core.app_registry import AppRegistryService
from backend.core.config import Config
from backend.core.database import Database
from backend.routes.web_tracking import _rewrite_html, _tracked_location


def make_config(tmp_path, apps=None):
    config_path = tmp_path / "apps.json"
    config_path.write_text(json.dumps(apps or []), encoding="utf-8")
    return Config(str(config_path))


def test_registry_reload_preserves_current_apps_when_json_is_invalid(tmp_path):
    config = make_config(tmp_path, [{"id": "kept", "name": "Kept", "type": "desktop"}])
    (tmp_path / "apps.json").write_text("{invalid", encoding="utf-8")

    try:
        config.reload()
        assert False, "reload should reject invalid JSON"
    except json.JSONDecodeError:
        pass

    assert config.get_app_by_id("kept") is not None


def test_registry_reload_rejects_structurally_invalid_apps(tmp_path):
    config = make_config(tmp_path, [{"id": "kept", "name": "Kept", "type": "desktop"}])
    (tmp_path / "apps.json").write_text("[1]", encoding="utf-8")

    try:
        config.reload()
        assert False, "reload should reject non-object apps"
    except ValueError:
        pass

    assert config.get_app_by_id("kept") is not None


def test_discovery_and_dummy_lifecycle_are_confined_to_apps_directory(tmp_path):
    config = make_config(tmp_path)
    candidate_dir = tmp_path / "apps" / "report-web"
    candidate_dir.mkdir(parents=True)
    (candidate_dir / "run.sh").write_text("#!/bin/sh\n", encoding="ascii")
    service = AppRegistryService(config)

    suggestions = service.discover()
    assert [item["id"] for item in suggestions] == ["report-web"]
    assert suggestions[0]["type"] == "web"

    dummy = service.create_dummy("cli")
    dummy_folder = tmp_path / "apps" / dummy["id"]
    assert dummy_folder.is_dir()
    assert config.get_app_by_id(dummy["id"])["dummy"] is True

    removed = config.remove_apps(service.dummy_ids())
    assert service.remove_dummy_files(removed) == 1
    assert not dummy_folder.exists()
    assert candidate_dir.exists()


def test_discovery_registration_drops_client_controlled_dummy_marker(tmp_path):
    config = make_config(tmp_path)
    candidate_dir = tmp_path / "apps" / "dummy-production"
    candidate_dir.mkdir(parents=True)
    launch_file = candidate_dir / "run.sh"
    launch_file.write_text("#!/bin/sh\n", encoding="ascii")
    service = AppRegistryService(config)

    app = service.validate_suggestion({
        "id": "dummy-production",
        "name": "Production",
        "type": "desktop",
        "exe": "apps/dummy-production/run.sh",
        "dummy": True,
        "cwd": "/tmp",
    })
    config.add_app(app)

    assert "dummy" not in app
    assert "cwd" not in app
    assert service.dummy_ids() == []
    assert service.remove_dummy_files([app]) == 0
    assert candidate_dir.exists()


class TrackingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body = b'<html><head></head><body><script src="/main.js"></script></body></html>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        elif self.path == "/api/items":
            body = b'{"items": []}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/plain-action":
            body = b"completed"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        elif self.path.startswith("/api/pdf?"):
            body = b"%PDF-1.4 test"
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
        else:
            body = b"not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def test_tracked_web_proxy_rewrites_html_and_records_api_calls(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), TrackingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        config = make_config(tmp_path, [{
            "id": "tracked-web",
            "name": "Tracked Web",
            "type": "web",
            "url": f"http://127.0.0.1:{port}",
            "auto_start": False,
        }])
        database = Database(str(tmp_path / "usage.db"))
        database.initialize()

        with TestClient(create_app(config, database)) as client:
            page = client.get("/tracked/tracked-web/", headers={"host": "tracked.localhost"})
            assert page.status_code == 200
            assert '/tracked/tracked-web/__apppilot_origin__/main.js' in page.text
            assert "window.fetch" in page.text
            assert f"const upstream='http://127.0.0.1:{port}'" in page.text

            api_response = client.get("/tracked/tracked-web/api/items", headers={"host": "tracked.localhost"})
            assert api_response.status_code == 200
            events = client.get("/api/usage/events?app_id=tracked-web").json()["events"]
            assert len(events) == 1
            assert events[0]["event_name"] == "web_api_called"
            details = json.loads(events[0]["details_json"])
            assert details["route"] == "/api/items"
            assert details["status_code"] == 200

            plain_response = client.get(
                "/tracked/tracked-web/__apppilot_origin__/plain-action",
                headers={"host": "tracked.localhost", "x-apppilot-activity": "fetch"},
            )
            assert plain_response.status_code == 200
            events = client.get("/api/usage/events?app_id=tracked-web").json()["events"]
            assert len(events) == 2
            assert json.loads(events[0]["details_json"])["route"] == "/plain-action"

            pdf_response = client.get(
                "/tracked/tracked-web/__apppilot_origin__/api/pdf?relative_path=123.pdf",
                headers={"host": "tracked.localhost"},
            )
            assert pdf_response.status_code == 200
            events = client.get("/api/usage/events?app_id=tracked-web").json()["events"]
            assert len(events) == 3
            pdf_details = json.loads(events[0]["details_json"])
            assert pdf_details["route"] == "/api/pdf"
            assert "relative_path" not in pdf_details
            blocked = client.get("/api/apps", headers={"host": "tracked.localhost"})
            assert blocked.status_code == 403
            csrf = client.post(
                "/api/registry/reload",
                headers={"host": "127.0.0.1", "origin": "http://tracked.localhost:9700"},
            )
            assert csrf.status_code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_tracking_bridge_routes_requests_without_marking_external_calls():
    if not shutil.which("node"):
        pytest.skip("Node is required to execute the injected browser bridge")
    html = _rewrite_html(
        b"<html><head></head></html>",
        "tracked-web",
        "utf-8",
        "http://127.0.0.1:8788/base/",
    ).decode()
    bridge = re.search(r"<script>([\s\S]*?)</script>", html).group(1)
    script = r'''
const calls=[];
global.window=global;
global.location=new URL('http://tracked.localhost:9700/tracked/tracked-web/');
global.fetch=(input,options)=>{calls.push({url:input instanceof Request?input.url:String(input),marker:options&&new Headers(options.headers).get('X-AppPilot-Activity')});return Promise.resolve({});};
class XHR { open(method,url){this.url=url;} setRequestHeader(key,value){this.marker=value;} send(){calls.push({url:this.url,marker:this.marker});} }
global.XMLHttpRequest=XHR;
eval(process.env.BRIDGE);
(async()=>{
  await fetch('/plain-action');
  await fetch(new Request('http://tracked.localhost:9700/request-action',{method:'POST',body:'x'}));
  await fetch('http://127.0.0.1:8788/absolute-action');
  await fetch('https://external.test/data');
  const xhr=new XMLHttpRequest();xhr.open('GET','/xhr-action');xhr.send();
  const externalXhr=new XMLHttpRequest();externalXhr.open('GET','https://external.test/xhr');externalXhr.send();
  const expected=[
    ['/tracked/tracked-web/__apppilot_origin__/plain-action','fetch'],
    ['http://tracked.localhost:9700/tracked/tracked-web/__apppilot_origin__/request-action','fetch'],
    ['/tracked/tracked-web/__apppilot_origin__/absolute-action','fetch'],
    ['https://external.test/data',null],
    ['/tracked/tracked-web/__apppilot_origin__/xhr-action','xhr'],
    ['https://external.test/xhr',null],
  ];
  if(JSON.stringify(calls.map(c=>[c.url,c.marker]))!==JSON.stringify(expected)){console.error(calls);process.exit(1);}
})().catch(error=>{console.error(error);process.exit(1);});
'''
    env = dict(os.environ, BRIDGE=bridge)
    subprocess.run(["node", "-e", script], env=env, check=True, capture_output=True, text=True)


def test_tracked_redirect_preserves_root_and_base_relative_locations():
    base_url = "http://127.0.0.1:8788/base/"

    assert _tracked_location("/login", base_url, "web") == "/tracked/web/__apppilot_origin__/login"
    assert _tracked_location("next", base_url, "web") == "next"
    assert _tracked_location("../login", base_url, "web") == "../login"
    assert _tracked_location("https://external.test/login", base_url, "web") == "https://external.test/login"
