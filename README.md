# AppPilot

**Portable local web app for launching, monitoring, and collecting usage data from internal EXE-based tools.**

## Overview

AppPilot is a desktop application that provides a local web dashboard for managing internal tools. Users simply double-click `AppPilot.exe` to launch a web server and browser interface for controlling configured applications.

### Key Features

- **One-click app launching** - Start/stop/restart configured EXE tools from a web dashboard
- **Process monitoring** - Track CPU, RAM, uptime, and detect crashes
- **Port monitoring** - Verify web apps are listening on expected ports
- **Health checks** - Call health endpoints and record response times
- **Usage logging** - Store session data in local SQLite database
- **Event tracking** - Apps can send usage events via local API
- **Weekly exports** - Generate ZIP packages for admin collection
- **Admin tool** - Import and analyze reports from multiple users

## Quick Start

1. Download and extract AppPilot
2. Configure apps in `apps.json`
3. Double-click `AppPilot.exe`
4. Browser opens to `http://127.0.0.1:9700`

## Configuration

Edit `apps.json` to configure your tools:

```json
[
  {
    "id": "file-preview",
    "name": "File Preview",
    "type": "web",
    "exe": "apps/file-preview/FilePreview.exe",
    "port": 8787,
    "url": "http://127.0.0.1:8787",
    "health_url": "http://127.0.0.1:8787/health",
    "auto_start": true,
    "monitor": {
      "process": true,
      "port": true,
      "http": true,
      "cpu_ram": true,
      "events": true
    }
  }
]
```

### App Types

- **desktop** - Standard GUI application
- **web** - Local web app (has port and health_url)
- **api** - Backend service without UI
- **external** - Already running externally (monitor only)

## Tech Stack

- **Backend**: Python FastAPI
- **Frontend**: HTML + HTMX + CSS/JS
- **Database**: SQLite
- **Packaging**: PyInstaller

## Project Structure

```
apppilot/
├── apppilot/              # Main application package
│   ├── main.py           # Entry point (PyInstaller)
│   ├── backend/          # FastAPI backend
│   │   ├── app.py        # FastAPI instance
│   │   ├── routes/       # API endpoints
│   │   ├── models/       # Pydantic schemas
│   │   ├── core/         # Core modules
│   │   │   ├── database.py   # SQLite operations
│   │   │   ├── process_manager.py
│   │   │   ├── monitor.py
│   │   │   └── config.py
│   │   └── utils/
│   └── web/              # Frontend files
│       ├── index.html
│       ├── apps.html
│       ├── usage.html
│       ├── export.html
│       └── static/
├── admin/                # Admin tool package
│   └── main.py
├── PyInstaller/          # Build specs
├── apps.json             # App registry
└── requirements.txt
```

## API Endpoints

### Apps
- `GET /api/apps` - List all apps with status
- `GET /api/apps/{id}/status` - Get app details
- `POST /api/apps/{id}/start` - Start app
- `POST /api/apps/{id}/stop` - Stop app
- `POST /api/apps/{id}/restart` - Restart app
- `GET /api/apps/{id}/logs` - Get recent logs

### Usage
- `GET /api/usage/summary?days=7` - Get usage summary
- `POST /api/usage/export-weekly` - Export to ZIP
- `GET /api/usage/sessions` - List sessions
- `GET /api/usage/events` - List usage events

### Events
- `POST /api/events` - Receive app events

## Development

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run from Source

```bash
python apppilot/main.py
```

### Build Executables

```bash
pyinstaller PyInstaller/apppilot.spec
pyinstaller PyInstaller/admin.spec
```

## Database Schema

### apps
- `app_id` - Unique app identifier
- `name` - Display name
- `type` - App type (desktop/web/api/external)
- `exe_path` - Path to executable
- `port` - Port number (if web)
- `created_at` / `updated_at`

### app_sessions
- `app_id` - Reference to app
- `machine_id` - Machine identifier
- `started_at` / `stopped_at` - Session timestamps
- `duration_sec` - Calculated runtime
- `exit_code` - Process exit code
- `crash_detected` - Boolean

### process_metrics
- `app_id` - Reference to app
- `timestamp` - When sampled
- `cpu_percent` / `memory_mb` - Resource usage
- `process_id` - PID at sampling time

### health_checks
- `app_id` - Reference to app
- `port` - Port checked
- `status` - open/closed/healthy/unhealthy
- `response_ms` - Response time

### usage_events
- `app_id` - Reference to app
- `event_name` - Event type
- `details_json` - Event metadata
- `success` - Boolean
- `machine_id` / `user_alias`

## Privacy

AppPilot is designed to avoid collecting sensitive information:

- No full file paths stored
- No file contents logged
- No personal data collected by default
- Machine ID is anonymous hash

## License

MIT License

## Support

See PROJECT.md for full architecture and requirements documentation.