"""
Configuration management for AppPilot.

Handles loading and saving configuration from apps.json and internal settings.
"""

import json
import os
import sys
import socket
from pathlib import Path
from typing import Any, Dict, Optional


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

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._apps = data
                        self._config['apps'] = data
                    else:
                        self._config = data
                        self._apps = data.get('apps', [])
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
            print(f"Error loading config: {e}")
            self._apps = []
            self._config = self._get_default_config()

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
        try:
            config_dir = Path(self.config_path).parent
            config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                if isinstance(self._apps, list) and all(isinstance(a, dict) and 'id' in a for a in self._apps):
                    json.dump(self._apps, f, indent=2)
                else:
                    json.dump(self._config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_machine_id(self) -> str:
        """Get the unique machine ID."""
        return self._config.get('machine_id', self._generate_machine_id())

    def get_user_alias(self) -> str:
        """Get the user alias (typically hostname or username)."""
        return socket.gethostname()

    def reload(self) -> None:
        """Reload configuration from file."""
        self._load_config()

    def is_port_available(self, port: int) -> bool:
        """Check if a port is available."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) != 0