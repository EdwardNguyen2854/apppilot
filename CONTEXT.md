# AppPilot Domain Glossary

## Core Concepts

| Term | Definition |
|---|---|
| **App** | Any resource in the unified registry (`apps.json`). Types: `desktop`, `web`, `api`, `external`, `mcp`, `cli`. |
| **App Registry** | The `apps.json` file — a unified JSON array of all app definitions. |
| **Type** | The category of an app: `desktop` (GUI EXE), `web` (local web app), `api`/`background` (headless service), `external` (already running, monitor-only), `mcp` (MCP server), `cli` (run-once tool). |

## MCP (Model Context Protocol)

| Term | Definition |
|---|---|
| **MCP Server** | An app with `type: "mcp"`. Runs as a subprocess (stdio transport) or connects to a remote SSE endpoint. Exposes tools, resources, and prompts via JSON-RPC. |
| **Transport** | Protocol wire format for an MCP server — `"stdio"` (subprocess stdin/stdout) or `"sse"` (HTTP Server-Sent Events). Default: `"stdio"`. |
| **MCPClient** | Class managing MCP JSON-RPC lifecycle: connect, initialize handshake, list tools/resources/prompts, call tool, disconnect. |
| **MCP Handshake** | The JSON-RPC `initialize` / `initialized` exchange establishing protocol version and capabilities. |

## CLI

| Term | Definition |
|---|---|
| **CLI Tool** | An app with `type: "cli"`. A run-once executable with configurable args, working directory, and timeout. |
| **CLI Execution** | One-shot subprocess run with captured stdout, stderr, and exit code. |

## Monitoring

| Term | Definition |
|---|---|
| **Process Monitoring** | Tracking whether a managed subprocess is alive (PID check). |
| **Port Check** | TCP connection test to a configured port. |
| **Health URL** | HTTP GET to a configured endpoint, recording response status and latency. |
| **Resource Metrics** | CPU and RAM usage sampling for running processes. |
| **Crash Event** | An abnormal app exit detected by the monitor. |

## Usage Tracking

| Term | Definition |
|---|---|
| **Usage Event** | A structured event reported by an app via the event API (e.g. `file_opened`, `tool_called`). |
| **Session** | A managed app lifecycle — from `start` to `stop`. Tracks duration, exit code, crash status. |
| **Weekly Export** | A ZIP package containing session, event, health, and metric data for a given ISO week. |

## Admin

| Term | Definition |
|---|---|
| **Admin Dashboard** | Separate tool for importing weekly ZIP packages and viewing aggregated reports across users. |
| **Master Tables** | Admin-side SQLite tables storing imported data from multiple machines. |
