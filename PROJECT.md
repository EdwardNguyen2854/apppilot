# AppPilot

**A local control center for all your tools — EXE apps, MCP servers, CLI tools, and external services — with usage tracking, effort-savings analytics, and weekly reports.**

Users double-click `AppPilot.exe`, a browser opens to `http://127.0.0.1:9700`, and everything they need is there: start/stop tools, monitor health, view logs, track usage, and measure ROI.

## Supported Resource Types

| Type | Description |
|---|---|
| **Desktop EXE** | Standard GUI applications launched and monitored by AppPilot |
| **Web EXE** | Local web apps packaged as EXEs with port and health-URL monitoring |
| **API / Background EXE** | Headless services (e.g. MCP servers bundled as EXEs) |
| **External** | Already-running services (monitor-only: port check, health URL) |
| **CLI Tool** | Command-line executables or scripts managed like first-class apps |
| **MCP Server** | Model Context Protocol servers (stdio or HTTP transport) with tool discovery and proxy invocation |

## Capabilities

- **Unified dashboard** — one web UI to see, start, stop, and open every managed tool.
- **Process supervision** — launch, restart, stop, crash detection, and log viewing.
- **Health monitoring** — port checks, HTTP health endpoints, CPU/RAM sampling.
- **Usage tracking** — automatic session logging plus an event API for apps to report feature usage.
- **Effort-savings analytics** — per-tool formulas calculate time/money saved, aggregated across users.
- **MCP protocol support** — discover tools/resources, invoke tools through AppPilot as a proxy.
- **CLI execution** — run CLI tools with arguments, enforce timeouts, capture output and exit codes.
- **Weekly exports** — ZIP packages for admin aggregation (sessions, events, metrics, savings).
- **Admin aggregation** — import reports from multiple users, view trends, export Excel/CSV.
- **Future: real-time dashboard** — SSE/WebSocket live status grid and time-series charts.
- **Future: central server** — multi-user aggregation with team dashboards.

## Design Principles

- **Portable** — runs from a folder, no installation required.
- **No-admin** — does not require administrator rights.
- **Offline-first** — works entirely without internet access.
- **Local-first data** — usage stored in local SQLite; nothing leaves the machine unless exported.
- **Safe binding** — binds only to `127.0.0.1` by default; LAN mode optional and password-protected.
- **Packaged as EXE** — users need zero runtimes (no Python, Node, or Docker).
- **Privacy-aware** — no full file paths, file contents, or personal data collected by default.

## Target Users

- **End users** — anyone who runs multiple internal tools and wants one place to manage them.
- **Team leads / managers** — want visibility into tool adoption and effort saved.
- **Admins** — collect reports across machines, measure ROI, identify unused or failing tools.
