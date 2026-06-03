# AppPilot — Architecture and Requirements

## 1. Product Definition

**AppPilot** is a portable local web app for launching, monitoring, and collecting usage data from internal EXE-based tools.

Users do not need to install Python, Node.js, Docker, or run any commands. They only double-click:

```text
AppPilot.exe
```

Then AppPilot starts a local web server and opens the dashboard in the browser:

```text
http://127.0.0.1:9700
```

AppPilot manages tools that may be:

```text
Desktop EXE apps
Local web EXE apps
API/background EXE apps
External/manual apps
```

---

## 2. Main Goals

AppPilot should:

1. Provide one web dashboard for all internal tools.
2. Run locally from `AppPilot.exe`.
3. Support both desktop apps and localhost web apps.
4. Start, stop, restart, and open configured tools.
5. Monitor process status, port status, health URLs, CPU, RAM, crashes, and logs.
6. Store usage data locally in each user’s own SQLite database.
7. Export weekly usage data for admin collection.
8. Allow an admin tool to import reports from multiple users.
9. Work without admin rights.
10. Work without internet access.
11. Avoid collecting sensitive information by default.

---

## 3. User Experience

Normal user workflow:

```text
1. User double-clicks AppPilot.exe
2. Browser opens http://127.0.0.1:9700
3. User sees all available tools
4. User starts/opens tools from the dashboard
5. AppPilot monitors usage in the background
6. End of week, user exports usage report
```

Admin workflow:

```text
1. Admin opens AppPilotAdmin.exe
2. Admin imports weekly ZIP reports from users
3. Admin reviews usage dashboard
4. Admin exports Excel/CSV summary
```

---

## 4. High-Level Architecture

```text
AppPilot.exe
│
├─ Local Web Server
│  ├─ FastAPI backend
│  ├─ Web dashboard
│  └─ REST API
│
├─ Web Frontend
│  ├─ App cards
│  ├─ Start / Stop / Restart buttons
│  ├─ Open browser button
│  ├─ Logs viewer
│  ├─ Usage summary
│  ├─ Settings page
│  └─ Weekly export page
│
├─ App Registry
│  └─ apps.json
│
├─ Process Manager
│  ├─ Start EXE
│  ├─ Stop process
│  ├─ Restart process
│  ├─ Track PID
│  └─ Detect crash
│
├─ Monitor Engine
│  ├─ Process monitor
│  ├─ Port monitor
│  ├─ HTTP health checker
│  ├─ CPU/RAM monitor
│  └─ Log monitor
│
├─ Usage Event Receiver
│  └─ POST /api/events
│
├─ Local Database
│  └─ data/usage.db
│
├─ Export Engine
│  └─ exports/usage_YYYY-WW_MACHINE.zip
│
└─ Admin Importer
   ├─ Import weekly ZIP files
   ├─ Merge data into master DB
   └─ Export Excel/CSV report
```

---

## 5. Local Web App Rule

AppPilot should bind only to localhost:

```text
127.0.0.1
```

Recommended URL:

```text
http://127.0.0.1:9700
```

Do not expose AppPilot to LAN by default because it can start and stop local EXE files.

Avoid this by default:

```text
0.0.0.0:9700
```

LAN mode can be added later only with password protection.

---

## 6. Supported App Types

### 6.1 Desktop App

Normal GUI EXE tool.

Examples:

```text
ClipboardOverlay.exe
KeystrokeViewer.exe
TranscriptionEditor.exe
```

Supported actions:

```text
Start
Stop
Restart
View logs
Track usage
```

Monitoring:

```text
Process running
CPU/RAM
Runtime
Crash detection
Optional feature events
```

---

### 6.2 Web App

Local web app packaged as EXE.

Examples:

```text
FilePreview.exe → http://127.0.0.1:8787
RagDashboard.exe → http://127.0.0.1:8080
```

Supported actions:

```text
Start
Stop
Restart
Open browser
View logs
Track usage
```

Monitoring:

```text
Process running
Port open
Health URL response
Response time
CPU/RAM
Crash detection
Optional feature events
```

---

### 6.3 API / Background App

Backend service without user-facing UI.

Examples:

```text
ExcelMcp.exe
CreoMcp.exe
RagApi.exe
```

Supported actions:

```text
Start
Stop
Restart
View logs
Track API/tool usage
```

Monitoring:

```text
Process running
Port/API health
Tool call count
Error count
CPU/RAM
Logs
```

---

### 6.4 External App

App started manually outside AppPilot.

Examples:

```text
LM Studio
Ollama
Existing company software
```

Supported actions:

```text
Check status
Open URL
View connection status
```

Monitoring:

```text
Port check
Health URL check
No start/stop unless configured
```

---

## 7. Folder Structure

```text
AppPilot/
├─ AppPilot.exe
├─ apps.json
├─ data/
│  └─ usage.db
├─ logs/
│  ├─ apppilot.log
│  ├─ FilePreview.log
│  └─ RagDashboard.log
├─ exports/
│  └─ usage_2026-W23_NCPC.zip
├─ apps/
│  ├─ file-preview/
│  │  └─ FilePreview.exe
│  ├─ rag-dashboard/
│  │  └─ RagDashboard.exe
│  ├─ clipboard-overlay/
│  │  └─ ClipboardOverlay.exe
│  └─ excel-mcp/
│     └─ ExcelMcp.exe
└─ admin/
   └─ AppPilotAdmin.exe
```

---

## 8. App Configuration

AppPilot loads app definitions from `apps.json`.

Example:

```json
[
  {
    "id": "file-preview",
    "name": "File Preview",
    "type": "web",
    "exe": "apps/file-preview/FilePreview.exe",
    "args": ["--port", "8787"],
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
  },
  {
    "id": "clipboard-overlay",
    "name": "Clipboard Overlay",
    "type": "desktop",
    "exe": "apps/clipboard-overlay/ClipboardOverlay.exe",
    "args": [],
    "auto_start": false,
    "monitor": {
      "process": true,
      "port": false,
      "http": false,
      "cpu_ram": true,
      "events": true
    }
  },
  {
    "id": "lm-studio",
    "name": "LM Studio",
    "type": "external",
    "port": 1234,
    "url": "http://127.0.0.1:1234/v1/models",
    "health_url": "http://127.0.0.1:1234/v1/models",
    "auto_start": false,
    "monitor": {
      "process": false,
      "port": true,
      "http": true,
      "cpu_ram": false,
      "events": false
    }
  }
]
```

---

## 9. Backend API

The frontend talks to the local backend API.

Core endpoints:

```text
GET  /api/apps
GET  /api/apps/{id}/status
POST /api/apps/{id}/start
POST /api/apps/{id}/stop
POST /api/apps/{id}/restart
GET  /api/apps/{id}/logs
GET  /api/usage/summary
POST /api/usage/export-weekly
POST /api/events
```

Example flow:

```text
User clicks Start File Preview
        ↓
Frontend calls POST /api/apps/file-preview/start
        ↓
Backend launches FilePreview.exe
        ↓
Monitor checks port 8787
        ↓
Frontend updates status to Online
```

---

## 10. Usage Logging Design

Each user has their own local database:

```text
data/usage.db
```

AppPilot records two kinds of usage data.

### 10.1 Automatic Monitoring Data

Collected by AppPilot without modifying the child apps.

Examples:

```text
App started
App stopped
App crashed
Runtime
Exit code
CPU usage
RAM usage
Port status
Health check status
Response time
```

### 10.2 App Event Data

Collected when each app sends usage events to AppPilot.

Event endpoint:

```text
POST http://127.0.0.1:9700/api/events
```

Example payload:

```json
{
  "app_id": "file-preview",
  "event": "file_opened",
  "details": {
    "file_type": "pdf",
    "file_size_mb": 12.4,
    "success": true
  }
}
```

Recommended events:

```text
app_opened
file_opened
folder_opened
search_used
export_clicked
export_success
export_failed
api_called
tool_called
tool_success
tool_failed
error_happened
```

Sensitive information should not be stored by default.

Avoid collecting:

```text
Full file paths
File contents
Customer names
Personal data
Keystrokes
Screenshots
```

Prefer safe metadata:

```text
File type
File size
Action name
Success/fail
Timestamp
App version
Machine alias
```

---

## 11. Database Schema

### apps

```text
id
app_id
name
type
version
exe_path
port
created_at
updated_at
```

### app_sessions

```text
id
app_id
machine_id
user_alias
started_at
stopped_at
duration_sec
exit_code
crash_detected
app_version
```

### process_metrics

```text
id
app_id
timestamp
cpu_percent
memory_mb
process_id
```

### health_checks

```text
id
app_id
timestamp
port
status
response_ms
error_message
```

### usage_events

```text
id
app_id
event_name
timestamp
details_json
success
app_version
machine_id
user_alias
```

### exports

```text
id
week_id
exported_at
file_name
record_count
status
```

---

## 12. Weekly Export Workflow

At the end of each week, AppPilot creates an export package:

```text
usage_2026-W23_NCPC.zip
```

Inside the ZIP:

```text
summary.json
events.csv
sessions.csv
health_checks.csv
process_metrics.csv
app_versions.json
```

Collection methods:

```text
Manual upload
Email
Shared folder
USB
Future central server API
```

Recommended first version:

```text
Export Weekly Usage button
```

Recommended later version:

```text
Auto-export every Friday to shared folder
```

---

## 13. Admin Tool

Admin uses:

```text
AppPilotAdmin.exe
```

It can also be a local web app launched through EXE:

```text
http://127.0.0.1:9701
```

Admin features:

```text
Import weekly ZIP files
Merge data into master database
Detect missing user reports
View usage dashboard
Export Excel/CSV summary
Filter by week, user, app, version
Compare app usage
View crash/error report
```

Admin dashboard should show:

```text
Most used apps
Least used apps
Total runtime by app
Active users by app
Crashes by app
Errors by version
Feature usage count
Users who did not submit weekly data
```

---

## 14. Functional Requirements

### FR-001 App Registry

AppPilot shall load app definitions from `apps.json`.

### FR-002 App Type Support

AppPilot shall support desktop, web, API/background, and external apps.

### FR-003 Local Web Dashboard

AppPilot shall provide a local web dashboard at `http://127.0.0.1:9700`.

### FR-004 EXE Launch

AppPilot shall start by double-clicking `AppPilot.exe`.

### FR-005 Start App

AppPilot shall allow users to start configured EXE apps.

### FR-006 Stop App

AppPilot shall allow users to stop apps started by AppPilot.

### FR-007 Restart App

AppPilot shall allow users to restart managed apps.

### FR-008 Open App

For web apps, AppPilot shall open the configured URL in the user’s default browser.

### FR-009 Process Monitoring

AppPilot shall detect whether a configured process is running.

### FR-010 Port Monitoring

AppPilot shall detect whether a configured port is open.

### FR-011 Health Check

AppPilot shall call configured health URLs and record response status and response time.

### FR-012 Resource Monitoring

AppPilot shall record CPU and RAM usage for managed apps.

### FR-013 Crash Detection

AppPilot shall detect abnormal app exits and record crash events.

### FR-014 Log Viewer

AppPilot shall provide a UI to view logs for each app.

### FR-015 Usage Event API

AppPilot shall provide a local event API for apps to send usage events.

### FR-016 Local Database

AppPilot shall store usage data in local SQLite database.

### FR-017 Weekly Export

AppPilot shall export weekly usage data to a ZIP package.

### FR-018 Admin Import

AppPilot Admin shall import weekly ZIP packages from users.

### FR-019 Admin Dashboard

AppPilot Admin shall show usage summary, errors, crashes, and app adoption.

### FR-020 Excel/CSV Export

AppPilot Admin shall export reports to Excel or CSV.

### FR-021 Privacy Control

AppPilot shall avoid collecting full file paths, file contents, personal data, or sensitive data unless explicitly enabled.

### FR-022 No-Install User Experience

AppPilot shall run as an EXE without requiring users to install Python, Node.js, or other runtimes.

---

## 15. Non-Functional Requirements

### NFR-001 Portable

AppPilot shall run from a folder without installation.

### NFR-002 No Admin Rights

AppPilot shall not require administrator permission for normal use.

### NFR-003 Offline-First

AppPilot shall work without internet access.

### NFR-004 Local-First Data

Usage data shall be stored locally on each user PC.

### NFR-005 Lightweight

AppPilot should use low CPU and memory when monitoring apps.

### NFR-006 Reliable

AppPilot should continue running even if child apps crash.

### NFR-007 Safe Localhost Binding

AppPilot should bind only to `127.0.0.1` by default.

### NFR-008 Configurable

Apps should be configurable through `apps.json` or a settings UI.

### NFR-009 Version Tracking

AppPilot should record app versions to support debugging and adoption analysis.

### NFR-010 Easy Distribution

The full package should be distributable as a ZIP or installer.

---

## 16. Recommended MVP

The first version should include:

```text
AppPilot.exe
Local web dashboard
apps.json
App cards
Start / Stop / Restart
Open web app button
Process status
Port status
Health check
Local SQLite logging
Weekly export ZIP
Basic admin importer
CSV/Excel export
```

Do not build auto-update, central server, or advanced permission system in MVP.

---

## 17. Phase Plan

### Phase 1 — AppPilot User MVP

```text
AppPilot.exe launches local web app
Load apps.json
Show app cards
Start/stop/restart apps
Open web URLs
Monitor process/port/health
Store app sessions in SQLite
Export weekly ZIP
```

### Phase 2 — Usage Events

```text
Add local event API
Add event tracking helper for apps
Record feature usage
Show usage charts
```

### Phase 3 — Admin Tool

```text
Build AppPilotAdmin.exe
Launch admin local web dashboard
Import weekly ZIP files
Merge into master DB
Show summary dashboard
Export Excel/CSV
```

### Phase 4 — Auto Collection

```text
Auto-export to shared folder
Detect duplicate imports
Detect missing reports
Add app version tracking
```

### Phase 5 — Advanced Features

```text
Auto-update tools
Role-based access
Password protection
Optional LAN mode
Central server upload
Crash report viewer
App dependency management
```

---

## 18. Recommended Tech Stack

### MVP stack

```text
Backend: Python FastAPI
Frontend: HTML + HTMX or React
Database: SQLite
Packaging: PyInstaller
Reports: CSV/XLSX export
```

Reason:

```text
Users only run EXE
No Python install needed
Easy to manage local EXE apps
Easy to make local APIs
Easy to export SQLite/CSV/Excel reports
Good fit with existing Python-based tools
```

### Alternative polished stack

```text
Tauri + Rust backend + SQLite
```

Reason:

```text
More professional desktop packaging
Lower memory usage
Better long-term desktop app feel
More complex to develop
```

Recommended for first version:

```text
Python + FastAPI + simple web UI + PyInstaller
```

---

## 19. Key Design Decision

AppPilot is not a cloud web app.

AppPilot is:

```text
A local web app packaged as an EXE.
```

It should behave like this:

```text
User double-clicks AppPilot.exe
        ↓
Local server starts
        ↓
Browser opens
        ↓
User manages all tools from web dashboard
```

AppPilot should be:

```text
EXE launcher
Process supervisor
Local web app monitor
Usage logger
Weekly report exporter
Admin reporting tool
```
