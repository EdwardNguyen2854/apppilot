"""App discovery and disposable dummy-tool management."""

import re
import shutil
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


SUPPORTED_DUMMY_TYPES = {"desktop", "web", "api", "cli", "mcp"}
LEGACY_DUMMY_IDS = {"dummy-desktop", "dummy-web", "dummy-api", "dummy-cli", "dummy-mcp"}
DISCOVERY_FIELDS = {
    "id", "name", "type", "description", "exe", "args", "port", "url",
    "health_url", "auto_start", "log_file", "monitor", "transport", "timeout",
}


class AppRegistryService:
    def __init__(self, config):
        self.config = config
        self.root = Path(config.config_path).resolve().parent
        self.apps_dir = self.root / "apps"

    def discover(self) -> List[Dict[str, Any]]:
        """Suggest app folders whose launch file is not in the registry."""
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        registered_ids = {app.get("id") for app in self.config.get_apps()}
        registered_paths = {
            self._resolve_registry_path(app.get("exe", ""))
            for app in self.config.get_apps()
            if app.get("exe")
        }
        suggestions = []
        for folder in sorted(self.apps_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith(".") or folder.name in registered_ids:
                continue
            launch_file = self._find_launch_file(folder)
            if launch_file is None or launch_file.resolve() in registered_paths:
                continue
            app_type = self._infer_type(folder, launch_file)
            app_id = self._slugify(folder.name)
            suggestion = self._base_definition(app_id, folder.name.replace("-", " ").title(), app_type, launch_file)
            suggestions.append(suggestion)
        return suggestions

    def validate_suggestion(self, app: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a discovery suggestion before adding it to the registry."""
        app_id = self._slugify(str(app.get("id", "")))
        app_type = app.get("type")
        exe = str(app.get("exe", ""))
        exe_path = self._resolve_registry_path(exe)
        if not app_id or app_type not in SUPPORTED_DUMMY_TYPES | {"external", "background"}:
            raise ValueError("Invalid app id or type")
        if not exe or not self._is_inside_apps(exe_path) or not exe_path.is_file():
            raise ValueError("Executable must be an existing file inside the apps directory")
        clean = {key: value for key, value in app.items() if key in DISCOVERY_FIELDS}
        clean["id"] = app_id
        clean["name"] = str(app.get("name") or app_id)
        clean["exe"] = exe_path.relative_to(self.root).as_posix()
        clean.setdefault("args", [])
        clean.setdefault("auto_start", False)
        clean.setdefault("log_file", f"logs/{app_id}.log")
        clean.setdefault("monitor", self._monitor_for(app_type))
        return clean

    def create_dummy(self, app_type: str) -> Dict[str, Any]:
        if app_type not in SUPPORTED_DUMMY_TYPES:
            raise ValueError(f"Unsupported dummy type: {app_type}")

        self.apps_dir.mkdir(parents=True, exist_ok=True)
        index = 1
        while True:
            app_id = f"dummy-{app_type}-{index}"
            folder = self.apps_dir / app_id
            if not folder.exists() and not self.config.get_app_by_id(app_id):
                break
            index += 1

        folder.mkdir()
        port = self._available_port() if app_type in {"web", "api"} else None
        try:
            (folder / "app.py").write_text(self._dummy_python(app_id, app_type, port), encoding="utf-8")
            (folder / "run.bat").write_text('@echo off\npython "%~dp0app.py" %*\n', encoding="ascii")
            (folder / "run.sh").write_text('#!/bin/sh\nexec python3 "$(dirname "$0")/app.py" "$@"\n', encoding="ascii")
            (folder / "run.sh").chmod(0o755)
            (folder / ".apppilot-dummy").write_text(app_id + "\n", encoding="ascii")
            launch_file = folder / ("run.bat" if sys.platform == "win32" else "run.sh")
            app = self._base_definition(app_id, f"Dummy {app_type.title()} {index}", app_type, launch_file)
            app["dummy"] = True
            if port:
                app.update({
                    "args": ["--port", str(port)],
                    "port": port,
                    "url": f"http://127.0.0.1:{port}",
                    "health_url": f"http://127.0.0.1:{port}/health",
                })
            if app_type == "mcp":
                app["transport"] = "stdio"
            if app_type == "cli":
                app["timeout"] = 30
            self.config.add_app(app)
            return app
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

    def remove_dummy_files(self, apps: List[Dict[str, Any]]) -> int:
        removed = 0
        for app in apps:
            exe_path = self._resolve_registry_path(app.get("exe", ""))
            folder = exe_path.parent
            marker = folder / ".apppilot-dummy"
            trusted_legacy = app.get("id") in LEGACY_DUMMY_IDS and folder.name == app.get("id")
            if self._is_dummy(app) and self._is_inside_apps(folder) and (marker.is_file() or trusted_legacy):
                if folder.exists():
                    shutil.rmtree(folder)
                removed += 1
        return removed

    def dummy_ids(self) -> List[str]:
        return [app["id"] for app in self.config.get_apps() if app.get("id") and self._is_dummy(app)]

    def _base_definition(self, app_id: str, name: str, app_type: str, launch_file: Path) -> Dict[str, Any]:
        return {
            "id": app_id,
            "name": name,
            "type": app_type,
            "description": f"Auto-detected {app_type} app" if not app_id.startswith("dummy-") else f"Generated dummy {app_type} tool",
            "exe": launch_file.resolve().relative_to(self.root).as_posix(),
            "args": [],
            "auto_start": False,
            "log_file": f"logs/{app_id}.log",
            "monitor": self._monitor_for(app_type),
        }

    @staticmethod
    def _monitor_for(app_type: str) -> Dict[str, bool]:
        networked = app_type in {"web", "api", "external"}
        process = app_type not in {"external", "mcp", "cli"}
        return {"process": process, "port": networked, "http": networked, "cpu_ram": process, "events": True}

    @staticmethod
    def _find_launch_file(folder: Path):
        preferred = ["run.bat", "run.sh"] if sys.platform == "win32" else ["run.sh", "run.bat"]
        for name in preferred:
            candidate = folder / name
            if candidate.is_file():
                return candidate
        for pattern in ("*.exe", "*.py"):
            candidates = sorted(folder.glob(pattern))
            if candidates:
                return candidates[0]
        return None

    @staticmethod
    def _infer_type(folder: Path, launch_file: Path) -> str:
        name = folder.name.lower()
        if "mcp" in name:
            return "mcp"
        if "cli" in name:
            return "cli"
        if "api" in name or "server" in name:
            return "api"
        if "web" in name:
            return "web"
        return "desktop"

    @staticmethod
    def _slugify(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    def _resolve_registry_path(self, value: str) -> Path:
        path = Path(value)
        return path.resolve() if path.is_absolute() else (self.root / path).resolve()

    def _is_inside_apps(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.apps_dir.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_dummy(app: Dict[str, Any]) -> bool:
        if app.get("dummy") is True:
            return True
        return app.get("id") in LEGACY_DUMMY_IDS

    def _available_port(self) -> int:
        configured = {app.get("port") for app in self.config.get_apps()}
        for port in range(8800, 9000):
            if port in configured:
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                if sock.connect_ex(("127.0.0.1", port)) != 0:
                    return port
        raise RuntimeError("No free dummy port available between 8800 and 8999")

    @staticmethod
    def _dummy_python(app_id: str, app_type: str, port: Optional[int]) -> str:
        if app_type in {"web", "api"}:
            return f'''import argparse\nimport json\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n\nclass Handler(BaseHTTPRequestHandler):\n    def _reply(self, status, payload):\n        body = json.dumps(payload).encode()\n        self.send_response(status)\n        self.send_header("Content-Type", "application/json")\n        self.send_header("Content-Length", str(len(body)))\n        self.end_headers()\n        self.wfile.write(body)\n\n    def do_GET(self):\n        if self.path == "/health":\n            self._reply(200, {{"status": "ok", "app": "{app_id}"}})\n        elif self.path.startswith("/api/"):\n            self._reply(200, {{"success": True, "path": self.path}})\n        elif self.path == "/":\n            body = b"<h1>{app_id}</h1><button onclick=\\"fetch('/api/example').then(r=>r.json()).then(console.log)\\">Call API</button>"\n            self.send_response(200)\n            self.send_header("Content-Type", "text/html")\n            self.send_header("Content-Length", str(len(body)))\n            self.end_headers()\n            self.wfile.write(body)\n        else:\n            self._reply(404, {{"error": "not found"}})\n\nparser = argparse.ArgumentParser()\nparser.add_argument("--port", type=int, default={port})\nargs = parser.parse_args()\nHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()\n'''
        if app_type == "mcp":
            return '''import json\nimport sys\n\nfor line in sys.stdin:\n    request = json.loads(line)\n    method = request.get("method")\n    if method == "notifications/initialized":\n        continue\n    result = {}\n    if method == "initialize":\n        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "dummy", "version": "1.0"}}\n    elif method == "tools/list":\n        result = {"tools": [{"name": "echo", "description": "Echo text", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}}]}\n    elif method == "resources/list":\n        result = {"resources": []}\n    elif method == "prompts/list":\n        result = {"prompts": []}\n    elif method == "tools/call":\n        result = {"content": [{"type": "text", "text": str(request.get("params", {}).get("arguments", {}).get("text", ""))}]}\n    print(json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": result}), flush=True)\n'''
        if app_type == "cli":
            return 'import sys\nprint("Dummy CLI arguments:", sys.argv[1:])\n'
        return 'import time\nprint("Dummy desktop tool is running", flush=True)\nwhile True:\n    time.sleep(5)\n'
