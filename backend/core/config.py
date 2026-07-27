"""
Configuration management for AppPilot.

Handles loading and saving configuration from apps.json and internal settings.
"""

import json
import os
import sys
import socket
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


SUPPORTED_APP_TYPES = {'desktop', 'web', 'api', 'background', 'external', 'mcp', 'cli'}


class Config:
    """Configuration manager for AppPilot."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self._config: Dict[str, Any] = {}
        self._apps: list = []
        self._load_config()

    def _get_default_config_path(self) -> str:
        """Get the default configuration file path."""
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent
        else:
            # __file__ is /Volumes/KINGSTON/02_Projects/apppilot/backend/core/config.py
            # We need to go up 3 levels to get to project root: core -> backend -> apppilot -> project root
            base_dir = Path(__file__).parent.parent.parent
        return str(base_dir / "apps.json")

    def _load_config(self, strict: bool = False) -> None:
        """Load configuration from file."""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    raw_apps = data if isinstance(data, list) else data.get('apps') if isinstance(data, dict) else None
                    apps = self._validate_apps(raw_apps)
                    loaded_config = {} if isinstance(data, list) else dict(data)
                    loaded_config['apps'] = apps
                    self._apps = apps
                    self._config = loaded_config
            else:
                self._apps = []
                self._config['apps'] = []

            self._config.setdefault('host', '127.0.0.1')
            self._config.setdefault('port', 9700)
            self._config.setdefault('admin_port', 9701)
            self._config.setdefault('log_dir', 'logs')
            self._config.setdefault('data_dir', 'data')
            self._config.setdefault('exports_dir', 'exports')
            self._config.setdefault('machine_id', self._generate_machine_id())

        except Exception as e:
            if strict:
                raise
            print(f"Error loading config: {e}")
            self._apps = []
            self._config = self._get_default_config()

    @staticmethod
    def _validate_apps(apps: Any) -> list:
        if not isinstance(apps, list):
            raise ValueError("apps.json must contain a list of apps")
        ids = set()
        validated = []
        for index, app in enumerate(apps):
            if not isinstance(app, dict):
                raise ValueError(f"App at index {index} must be an object")
            app_id = app.get('id')
            app_type = app.get('type')
            if not isinstance(app_id, str) or not app_id.strip():
                raise ValueError(f"App at index {index} requires a non-empty id")
            if app_id in ids:
                raise ValueError(f"Duplicate app id: {app_id}")
            if app_type not in SUPPORTED_APP_TYPES:
                raise ValueError(f"Unsupported type for app {app_id}: {app_type}")
            ids.add(app_id)
            validated.append(app)
        return validated

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            'host': '127.0.0.1',
            'port': 9700,
            'admin_port': 9701,
            'log_dir': 'logs',
            'data_dir': 'data',
            'exports_dir': 'exports',
            'machine_id': self._generate_machine_id(),
            'apps': []
        }

    def _generate_machine_id(self) -> str:
        """Generate a unique machine ID."""
        try:
            hostname = socket.gethostname()
            import hashlib
            user = os.environ.get('USERNAME', os.environ.get('USER', 'unknown'))
            combined = f"{hostname}-{user}"
            return hashlib.md5(combined.encode()).hexdigest()[:12].upper()
        except Exception:
            return "UNKNOWN"

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        self._config[key] = value

    def get_apps(self) -> list:
        """Get the list of configured apps."""
        return self._apps

    def get_app_by_id(self, app_id: str) -> Optional[Dict]:
        """Get a specific app by its ID."""
        for app in self._apps:
            if app.get('id') == app_id:
                return app
        return None

    def save_config(self) -> None:
        """Save configuration to file."""
        config_path = Path(self.config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._apps if isinstance(self._apps, list) else self._config

        fd, temp_path = tempfile.mkstemp(
            dir=str(config_path.parent), prefix=f".{config_path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                f.write('\n')
            os.replace(temp_path, config_path)
        except Exception:
            if Path(temp_path).exists():
                Path(temp_path).unlink()
            raise

    def add_app(self, app: Dict[str, Any]) -> None:
        """Add an app to the registry and persist it."""
        self._validate_apps(self._apps + [app])
        app_id = app.get('id')
        if not app_id:
            raise ValueError("App id is required")
        if self.get_app_by_id(app_id):
            raise ValueError(f"App {app_id} is already registered")
        self._apps.append(app)
        self._config['apps'] = self._apps
        try:
            self.save_config()
        except Exception:
            self._apps.pop()
            raise

    def remove_apps(self, app_ids: list[str]) -> list[Dict[str, Any]]:
        """Remove apps from the registry and return the removed definitions."""
        ids = set(app_ids)
        removed = [app for app in self._apps if app.get('id') in ids]
        if not removed:
            return []
        previous = self._apps
        self._apps = [app for app in self._apps if app.get('id') not in ids]
        self._config['apps'] = self._apps
        try:
            self.save_config()
        except Exception:
            self._apps = previous
            self._config['apps'] = previous
            raise
        return removed

    def get_machine_id(self) -> str:
        """Get the unique machine ID."""
        return self._config.get('machine_id', self._generate_machine_id())

    def get_user_alias(self) -> str:
        """Get the user alias (typically hostname or username)."""
        return socket.gethostname()

    def reload(self) -> None:
        """Reload configuration from file."""
        previous_config = self._config
        previous_apps = self._apps
        try:
            self._config = {}
            self._apps = []
            self._load_config(strict=True)
        except Exception:
            self._config = previous_config
            self._apps = previous_apps
            raise

    def is_port_available(self, port: int) -> bool:
        """Check if a port is available."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) != 0
