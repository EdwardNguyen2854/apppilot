# AppPilot Requirements

## App Registry & Types

| ID | Requirement |
|---|---|
| FR-001 | AppPilot shall load app definitions from `apps.json`. |
| FR-002 | AppPilot shall support desktop, web, API/background, external, CLI, and MCP app types. |
| FR-003 | AppPilot shall provide a local web dashboard at `http://127.0.0.1:9700`. |
| FR-004 | AppPilot shall start by double-clicking `AppPilot.exe`. |
| FR-023 | Apps shall be configurable through `apps.json` or a settings UI. |

## Lifecycle Management

| ID | Requirement |
|---|---|
| FR-005 | AppPilot shall allow users to start configured apps. |
| FR-006 | AppPilot shall allow users to stop apps started by AppPilot. |
| FR-007 | AppPilot shall allow users to restart managed apps. |
| FR-008 | For web apps, AppPilot shall open the configured URL in the user's default browser. |

## Process Monitoring

| ID | Requirement |
|---|---|
| FR-009 | AppPilot shall detect whether a configured process is running. |
| FR-010 | AppPilot shall detect whether a configured port is open. |
| FR-011 | AppPilot shall call configured health URLs and record response status and response time. |
| FR-012 | AppPilot shall record CPU and RAM usage for managed apps. |
| FR-013 | AppPilot shall detect abnormal app exits and record crash events. |
| FR-014 | AppPilot shall provide a UI to view logs for each app. |

## Usage Tracking

| ID | Requirement |
|---|---|
| FR-015 | AppPilot shall provide a local event API for apps to send usage events. |
| FR-016 | AppPilot shall store usage data in local SQLite database. |
| FR-017 | AppPilot shall export weekly usage data to a ZIP package. |

## Admin

| ID | Requirement |
|---|---|
| FR-018 | AppPilot Admin shall import weekly ZIP packages from users. |
| FR-019 | AppPilot Admin shall show usage summary, errors, crashes, and app adoption. |
| FR-020 | AppPilot Admin shall export reports to Excel or CSV. |

## Privacy & UX

| ID | Requirement |
|---|---|
| FR-021 | AppPilot shall avoid collecting full file paths, file contents, personal data, or sensitive data unless explicitly enabled. |
| FR-022 | AppPilot shall run as an EXE without requiring users to install Python, Node.js, or other runtimes. |

## MCP Server Support

| ID | Requirement |
|---|---|
| FR-024 | AppPilot shall allow users to configure MCP server definitions in the app registry. |
| FR-025 | AppPilot shall start and stop MCP servers as subprocesses (stdio transport) or connect via HTTP (SSE transport). |
| FR-026 | AppPilot shall discover and list available MCP tools from each connected MCP server. |
| FR-027 | AppPilot shall discover and list available MCP resources and prompts from each server. |
| FR-028 | AppPilot shall allow users to invoke MCP tools through the dashboard, proxying arguments and returning results. |
| FR-029 | AppPilot shall monitor MCP server process health and protocol-level handshake status. |
| FR-030 | AppPilot shall log all MCP tool invocations with arguments, duration, success/failure, and result summary. |

## CLI Tool Support

| ID | Requirement |
|---|---|
| FR-031 | AppPilot shall allow users to configure CLI tool definitions including executable path, default arguments, working directory, and timeout. |
| FR-032 | AppPilot shall allow users to run CLI tools from the dashboard with optional argument overrides. |
| FR-033 | AppPilot shall capture stdout, stderr, and exit codes from CLI tool executions. |
| FR-034 | AppPilot shall enforce configurable timeouts on CLI tool executions and terminate hung processes. |
| FR-035 | AppPilot shall maintain a run history for each CLI tool showing who ran it, when, duration, exit code, and output summary. |

## Effort Savings Analytics

| ID | Requirement |
|---|---|
| FR-036 | AppPilot shall allow each app to define a savings formula (per-event minutes saved, or a default value). |
| FR-037 | AppPilot shall compute and store effort savings automatically based on usage events and the configured formula. |
| FR-038 | AppPilot shall display aggregated time saved per app, per user, and total (current week and all time). |
| FR-039 | AppPilot shall include effort savings data in weekly export packages. |
| FR-040 | AppPilot Admin shall display effort savings across all imported reports. |

## Real-time Dashboard

| ID | Requirement |
|---|---|
| FR-041 | AppPilot shall provide a real-time dashboard view with live status updates for all managed resources. |
| FR-042 | AppPilot shall use SSE or WebSocket to push status changes to the browser without polling. |
| FR-043 | The real-time dashboard shall show live process status, port status, health status, and resource metrics (CPU/RAM). |

## Central Server (Future)

| ID | Requirement |
|---|---|
| FR-044 | AppPilot shall support optional auto-upload of weekly exports to a central server endpoint. |
| FR-045 | The central server shall aggregate reports from multiple AppPilot instances into a unified database. |
| FR-046 | The central server shall provide team-wide dashboards, trend analysis, and effort-savings rollups. |

## Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-001 | AppPilot shall run from a folder without installation. |
| NFR-002 | AppPilot shall not require administrator permission for normal use. |
| NFR-003 | AppPilot shall work without internet access. |
| NFR-004 | Usage data shall be stored locally on each user PC. |
| NFR-005 | AppPilot should use low CPU and memory when monitoring apps. |
| NFR-006 | AppPilot should continue running even if child apps crash. |
| NFR-007 | AppPilot should bind only to `127.0.0.1` by default. |
| NFR-008 | AppPilot should record app versions to support debugging and adoption analysis. |
| NFR-009 | The full package should be distributable as a ZIP or installer. |
| NFR-010 | MCP tool invocations and CLI executions should have configurable timeouts to prevent hanging. |
