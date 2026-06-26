"""
SQLite database setup and operations for AppPilot.

Handles all database operations including:
- Schema creation
- Session management
- Usage event recording
- Health check logging
- Export tracking
"""

import sqlite3
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager for AppPilot."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            if getattr(sys, 'frozen', False):
                base_dir = Path(sys.executable).parent
            else:
                base_dir = Path(__file__).parent.parent
            db_path = str(base_dir / "data" / "usage.db")

        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_data_dir()

    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Initialize the database with required tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS apps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    version TEXT,
                    exe_path TEXT,
                    port INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    user_alias TEXT,
                    started_at TIMESTAMP NOT NULL,
                    stopped_at TIMESTAMP,
                    duration_sec INTEGER,
                    exit_code INTEGER,
                    crash_detected INTEGER DEFAULT 0,
                    app_version TEXT,
                    FOREIGN KEY (app_id) REFERENCES apps(app_id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS process_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    cpu_percent REAL,
                    memory_mb REAL,
                    process_id INTEGER,
                    FOREIGN KEY (app_id) REFERENCES apps(app_id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS health_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    port INTEGER,
                    status TEXT NOT NULL,
                    response_ms INTEGER,
                    error_message TEXT,
                    FOREIGN KEY (app_id) REFERENCES apps(app_id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details_json TEXT,
                    success INTEGER DEFAULT 1,
                    app_version TEXT,
                    machine_id TEXT,
                    user_alias TEXT,
                    FOREIGN KEY (app_id) REFERENCES apps(app_id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mcp_invocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT,
                    started_at TIMESTAMP NOT NULL,
                    duration_ms INTEGER,
                    success INTEGER DEFAULT 0,
                    result_summary TEXT,
                    error_message TEXT,
                    FOREIGN KEY (app_id) REFERENCES apps(app_id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cli_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id TEXT NOT NULL,
                    args_json TEXT,
                    exit_code INTEGER,
                    stdout_size INTEGER,
                    stderr_size INTEGER,
                    duration_sec REAL,
                    success INTEGER DEFAULT 0,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    error_message TEXT,
                    FOREIGN KEY (app_id) REFERENCES apps(app_id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS exports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_id TEXT NOT NULL,
                    exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_name TEXT,
                    record_count INTEGER,
                    status TEXT DEFAULT 'pending'
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_app_id ON app_sessions(app_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON app_sessions(started_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_app_id ON usage_events(app_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON usage_events(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mcp_invocations_app_id ON mcp_invocations(app_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mcp_invocations_started_at ON mcp_invocations(started_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cli_runs_app_id ON cli_runs(app_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cli_runs_started_at ON cli_runs(started_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_app_id ON process_metrics(app_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_app_id ON health_checks(app_id)")

            conn.commit()
            logger.info("Database initialized with all tables")

        # Initialize master database tables for admin imports
        self.initialize_master_db()

    def register_app(self, app_data: Dict[str, Any]) -> None:
        """Register a new app in the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO apps (app_id, name, type, version, exe_path, port, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                app_data.get('id'),
                app_data.get('name'),
                app_data.get('type'),
                app_data.get('version'),
                app_data.get('exe'),
                app_data.get('port')
            ))

    def start_session(self, app_id: str, machine_id: str, user_alias: str = None,
                      app_version: str = None) -> int:
        """Start a new app session and return the session ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO app_sessions (app_id, machine_id, user_alias, started_at, app_version)
                VALUES (?, ?, ?, ?, ?)
            """, (app_id, machine_id, user_alias, datetime.now(), app_version))
            return cursor.lastrowid

    def end_session(self, session_id: int, exit_code: int = 0, crash_detected: bool = False) -> None:
        """End an app session and calculate duration."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE app_sessions
                SET stopped_at = CURRENT_TIMESTAMP,
                    exit_code = ?,
                    crash_detected = ?
                WHERE id = ?
            """, (exit_code, 1 if crash_detected else 0, session_id))

            cursor.execute("""
                UPDATE app_sessions
                SET duration_sec = CAST((julianday(stopped_at) - julianday(started_at)) * 86400 AS INTEGER)
                WHERE id = ?
            """, (session_id,))

    def get_active_session(self, app_id: str) -> Optional[Dict]:
        """Get the current active session for an app, if any."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM app_sessions
                WHERE app_id = ? AND stopped_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
            """, (app_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def record_process_metric(self, app_id: str, cpu_percent: float,
                               memory_mb: float, process_id: int = None) -> None:
        """Record a process metric snapshot."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO process_metrics (app_id, cpu_percent, memory_mb, process_id, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (app_id, cpu_percent, memory_mb, process_id, datetime.now()))

    def record_health_check(self, app_id: str, port: int, status: str,
                            response_ms: int = None, error_message: str = None) -> None:
        """Record a health check result."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO health_checks (app_id, port, status, response_ms, error_message, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (app_id, port, status, response_ms, error_message, datetime.now()))

    def record_usage_event(self, app_id: str, event_name: str,
                           details: Dict = None, success: bool = True,
                           app_version: str = None, machine_id: str = None,
                           user_alias: str = None) -> None:
        """Record a usage event from an app."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO usage_events (app_id, event_name, details_json, success, app_version, machine_id, user_alias, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                app_id, event_name,
                json.dumps(details) if details else None,
                1 if success else 0,
                app_version, machine_id, user_alias, datetime.now()
            ))

    def record_mcp_invocation(self, app_id: str, tool_name: str,
                              arguments: Dict = None, started_at: datetime = None,
                              duration_ms: int = None, success: bool = False,
                              result_summary: str = None,
                              error_message: str = None) -> int:
        """Record an MCP tool invocation attempt."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO mcp_invocations (
                    app_id, tool_name, arguments_json, started_at, duration_ms,
                    success, result_summary, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                app_id,
                tool_name,
                json.dumps(arguments or {}),
                started_at or datetime.now(),
                duration_ms,
                1 if success else 0,
                result_summary,
                error_message,
            ))
            return cursor.lastrowid

    def list_mcp_invocations(self, app_id: str, limit: int = 50) -> List[Dict]:
        """Return recent MCP invocations newest first."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM mcp_invocations
                WHERE app_id = ?
                ORDER BY started_at DESC, id DESC
                LIMIT ?
            """, (app_id, limit))
            rows = []
            for row in cursor.fetchall():
                item = dict(row)
                try:
                    item["arguments"] = json.loads(item.get("arguments_json") or "{}")
                except json.JSONDecodeError:
                    item["arguments"] = {}
                item["args"] = item["arguments"]
                item["timestamp"] = item.get("started_at")
                item["success"] = bool(item.get("success"))
                rows.append(item)
            return rows

    def count_recent_mcp_invocations(self, app_id: str, since: datetime = None) -> int:
        """Count MCP invocations for an app since a timestamp."""
        if since is None:
            since = datetime.now() - timedelta(days=1)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) AS count
                FROM mcp_invocations
                WHERE app_id = ? AND started_at >= ?
            """, (app_id, since))
            row = cursor.fetchone()
            return int(row["count"] if row else 0)

    def record_cli_run(self, app_id: str, args: List[str] = None,
                       exit_code: int = None, stdout_size: int = 0,
                       stderr_size: int = 0, duration_sec: float = 0.0,
                       success: bool = False,
                       error_message: str = None) -> int:
        """Record a CLI tool execution. Returns the new row id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cli_runs (
                    app_id, args_json, exit_code, stdout_size, stderr_size,
                    duration_sec, success, started_at, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                app_id,
                json.dumps(args or []),
                exit_code,
                stdout_size,
                stderr_size,
                duration_sec,
                1 if success else 0,
                datetime.now(),
                error_message,
            ))
            return cursor.lastrowid

    def list_cli_runs(self, app_id: str, limit: int = 50) -> List[Dict]:
        """Return recent CLI runs newest first."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM cli_runs
                WHERE app_id = ?
                ORDER BY started_at DESC, id DESC
                LIMIT ?
            """, (app_id, limit))
            rows = []
            for row in cursor.fetchall():
                item = dict(row)
                try:
                    item["args"] = json.loads(item.get("args_json") or "[]")
                except json.JSONDecodeError:
                    item["args"] = []
                item["success"] = bool(item.get("success"))
                item["timestamp"] = item.get("started_at")
                stdout_size = item.get("stdout_size") or 0
                item["stdout_summary"] = f"{stdout_size} bytes"
                rows.append(item)
            return rows

    def get_last_cli_run(self, app_id: str) -> Optional[Dict]:
        """Return the most recent CLI run for an app, if any."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM cli_runs
                WHERE app_id = ?
                ORDER BY started_at DESC, id DESC
                LIMIT 1
            """, (app_id,))
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            try:
                item["args"] = json.loads(item.get("args_json") or "[]")
            except json.JSONDecodeError:
                item["args"] = []
            item["success"] = bool(item.get("success"))
            return item

    def record_export(self, week_id: str, file_name: str, record_count: int,
                      status: str = 'completed') -> None:
        """Record an export operation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO exports (week_id, file_name, record_count, status, exported_at)
                VALUES (?, ?, ?, ?, ?)
            """, (week_id, file_name, record_count, status, datetime.now()))

    def get_usage_summary(self, start_date: datetime = None, end_date: datetime = None) -> Dict:
        """Get usage summary for a time period."""
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=7)

        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    app_id,
                    COUNT(*) as session_count,
                    SUM(duration_sec) as total_runtime,
                    SUM(crash_detected) as crash_count
                FROM app_sessions
                WHERE started_at BETWEEN ? AND ?
                GROUP BY app_id
            """, (start_date, end_date))
            sessions = cursor.fetchall()

            cursor.execute("""
                SELECT app_id, COUNT(*) as event_count
                FROM usage_events
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY app_id
            """, (start_date, end_date))
            events = cursor.fetchall()

            return {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'sessions': [dict(row) for row in sessions],
                'events': [dict(row) for row in events]
            }

    def get_weekly_export_data(self, year: int, week: int) -> Dict[str, Any]:
        """Get all data for a specific week for export."""
        week_start = datetime.strptime(f'{year}-W{week:02d}-1', '%G-W%V-%u')
        week_end = week_start + timedelta(days=7)

        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM app_sessions
                WHERE started_at BETWEEN ? AND ?
            """, (week_start, week_end))
            sessions = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT * FROM usage_events
                WHERE timestamp BETWEEN ? AND ?
            """, (week_start, week_end))
            events = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT * FROM health_checks
                WHERE timestamp BETWEEN ? AND ?
            """, (week_start, week_end))
            health_checks = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT * FROM process_metrics
                WHERE timestamp BETWEEN ? AND ?
            """, (week_start, week_end))
            metrics = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT * FROM cli_runs
                WHERE started_at BETWEEN ? AND ?
            """, (week_start, week_end))
            cli_runs = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT DISTINCT app_id, app_version FROM app_sessions
                WHERE started_at BETWEEN ? AND ?
            """, (week_start, week_end))
            app_versions = {row['app_id']: row['app_version'] for row in cursor.fetchall()}

            return {
                'week_id': f"{year}-W{week:02d}",
                'generated_at': datetime.now().isoformat(),
                'sessions': sessions,
                'events': events,
                'health_checks': health_checks,
                'process_metrics': metrics,
                'cli_runs': cli_runs,
                'app_versions': app_versions
            }

    def get_all_apps(self) -> List[Dict]:
        """Get all registered apps."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM apps ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    def get_app_sessions(self, app_id: str, limit: int = 100) -> List[Dict]:
        """Get recent sessions for an app."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM app_sessions
                WHERE app_id = ?
                ORDER BY started_at DESC
                LIMIT ?
            """, (app_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def clear_old_data(self, days: int = 90) -> int:
        """Clear data older than specified days. Returns count of deleted rows."""
        cutoff_date = datetime.now() - timedelta(days=days)
        deleted = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM process_metrics WHERE timestamp < ?", (cutoff_date,))
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM health_checks WHERE timestamp < ?", (cutoff_date,))
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM usage_events WHERE timestamp < ?", (cutoff_date,))
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM mcp_invocations WHERE started_at < ?", (cutoff_date,))
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM cli_runs WHERE started_at < ?", (cutoff_date,))
            deleted += cursor.rowcount
            conn.commit()
            return deleted

    def clear_old_usage_data(self, cutoff_date: datetime) -> int:
        """Clear usage data older than a specific date. Returns count of deleted rows."""
        deleted = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM process_metrics WHERE timestamp < ?", (cutoff_date,))
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM health_checks WHERE timestamp < ?", (cutoff_date,))
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM usage_events WHERE timestamp < ?", (cutoff_date,))
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM mcp_invocations WHERE started_at < ?", (cutoff_date,))
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM cli_runs WHERE started_at < ?", (cutoff_date,))
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM app_sessions WHERE started_at < ?", (cutoff_date,))
            deleted += cursor.rowcount
            conn.commit()
            return deleted

    def reset_usage_data(self) -> int:
        """Delete all usage data from the database. Returns count of deleted rows."""
        deleted = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM process_metrics")
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM health_checks")
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM usage_events")
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM mcp_invocations")
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM cli_runs")
            deleted += cursor.rowcount
            cursor.execute("DELETE FROM app_sessions")
            deleted += cursor.rowcount
            conn.commit()
            return deleted

    # ========== Master Database / Admin Methods ==========

    def initialize_master_db(self) -> None:
        """Initialize tables for master database (admin imports)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Master sessions table for imported weekly data
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS master_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_id TEXT NOT NULL,
                    week_id TEXT NOT NULL,
                    app_id TEXT NOT NULL,
                    user_alias TEXT,
                    started_at TEXT NOT NULL,
                    stopped_at TEXT,
                    duration_sec INTEGER,
                    exit_code INTEGER,
                    crash_detected INTEGER DEFAULT 0,
                    app_version TEXT,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(machine_id, week_id, app_id, started_at)
                )
            """)

            # Master events table for imported weekly data
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS master_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_id TEXT,
                    app_id TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    details_json TEXT,
                    success INTEGER DEFAULT 1,
                    app_version TEXT,
                    user_alias TEXT,
                    week_id TEXT,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(machine_id, app_id, event_name, timestamp)
                )
            """)

            # Master health checks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS master_health_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_id TEXT,
                    app_id TEXT NOT NULL,
                    week_id TEXT,
                    timestamp TEXT NOT NULL,
                    port INTEGER,
                    status TEXT NOT NULL,
                    response_ms INTEGER,
                    error_message TEXT,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(machine_id, app_id, timestamp)
                )
            """)

            # Master metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS master_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_id TEXT,
                    app_id TEXT NOT NULL,
                    week_id TEXT,
                    timestamp TEXT NOT NULL,
                    cpu_percent REAL,
                    memory_mb REAL,
                    process_id INTEGER,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(machine_id, app_id, timestamp)
                )
            """)

            # Import history tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS import_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_id TEXT NOT NULL,
                    machine_id TEXT,
                    file_name TEXT,
                    records_imported INTEGER DEFAULT 0,
                    records_skipped INTEGER DEFAULT 0,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending'
                )
            """)

            # Create indexes for master tables
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_sessions_app_id ON master_sessions(app_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_sessions_week_id ON master_sessions(week_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_sessions_machine_id ON master_sessions(machine_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_events_app_id ON master_events(app_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_events_week_id ON master_events(week_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_import_history_week ON import_history(week_id)")

            conn.commit()
            logger.info("Master database tables initialized")

    def import_weekly_session(self, row: Dict) -> bool:
        """Import a session record from weekly ZIP. Returns True if inserted, False if duplicate."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO master_sessions
                    (machine_id, week_id, app_id, user_alias, started_at, stopped_at, duration_sec, exit_code, crash_detected, app_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('machine_id'),
                    row.get('week_id'),
                    row.get('app_id'),
                    row.get('user_alias'),
                    row.get('started_at'),
                    row.get('stopped_at'),
                    row.get('duration_sec'),
                    row.get('exit_code'),
                    1 if str(row.get('crash_detected', '0')).lower() in ('1', 'true', 'yes') else 0,
                    row.get('app_version')
                ))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error importing session: {e}")
            return False

    def import_weekly_event(self, row: Dict) -> bool:
        """Import an event record from weekly ZIP. Returns True if inserted, False if duplicate."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO master_events
                    (machine_id, app_id, event_name, timestamp, details_json, success, app_version, user_alias, week_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('machine_id'),
                    row.get('app_id'),
                    row.get('event_name'),
                    row.get('timestamp'),
                    row.get('details_json'),
                    1 if str(row.get('success', '1')).lower() in ('1', 'true', 'yes') else 0,
                    row.get('app_version'),
                    row.get('user_alias'),
                    row.get('week_id')
                ))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error importing event: {e}")
            return False

    def import_weekly_health_check(self, row: Dict) -> bool:
        """Import a health check record from weekly ZIP."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO master_health_checks
                    (machine_id, app_id, week_id, timestamp, port, status, response_ms, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('machine_id'),
                    row.get('app_id'),
                    row.get('week_id'),
                    row.get('timestamp'),
                    row.get('port'),
                    row.get('status'),
                    row.get('response_ms'),
                    row.get('error_message')
                ))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error importing health check: {e}")
            return False

    def import_weekly_metric(self, row: Dict) -> bool:
        """Import a metric record from weekly ZIP."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO master_metrics
                    (machine_id, app_id, week_id, timestamp, cpu_percent, memory_mb, process_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get('machine_id'),
                    row.get('app_id'),
                    row.get('week_id'),
                    row.get('timestamp'),
                    row.get('cpu_percent'),
                    row.get('memory_mb'),
                    row.get('process_id')
                ))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error importing metric: {e}")
            return False

    def record_import(self, week_id: str, machine_id: str, file_name: str,
                      records_imported: int, records_skipped: int, status: str = 'completed') -> None:
        """Record an import operation in history."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO import_history (week_id, machine_id, file_name, records_imported, records_skipped, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (week_id, machine_id, file_name, records_imported, records_skipped, status))

    def get_import_history(self, limit: int = 50) -> List[Dict]:
        """Get recent import history."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM import_history
                ORDER BY imported_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_admin_summary(self, app_id: Optional[str] = None, user: Optional[str] = None,
                          week_id: Optional[str] = None) -> Dict:
        """Get aggregated admin summary."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Base query conditions
            conditions = []
            params = []

            if app_id:
                conditions.append("app_id = ?")
                params.append(app_id)
            if user:
                conditions.append("user_alias = ?")
                params.append(user)
            if week_id:
                conditions.append("week_id = ?")
                params.append(week_id)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # Total sessions and runtime
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_sessions,
                    COALESCE(SUM(duration_sec), 0) as total_runtime_sec,
                    COALESCE(SUM(crash_detected), 0) as total_crashes
                FROM master_sessions
                WHERE {where_clause}
            """, params)
            session_stats = cursor.fetchone()

            # Total events
            cursor.execute(f"""
                SELECT COUNT(*) as total_events
                FROM master_events
                WHERE {where_clause.replace('user_alias', 'user_alias')}
            """, params)
            event_count = cursor.fetchone()['total_events']

            # Distinct users
            cursor.execute(f"""
                SELECT COUNT(DISTINCT user_alias) as total_users
                FROM master_sessions
                WHERE {where_clause}
            """, params)
            user_count = cursor.fetchone()['total_users']

            # Apps breakdown
            cursor.execute(f"""
                SELECT
                    app_id,
                    COUNT(*) as sessions,
                    COALESCE(SUM(duration_sec), 0) / 3600.0 as runtime_hours,
                    COALESCE(SUM(crash_detected), 0) as crashes
                FROM master_sessions
                WHERE {where_clause}
                GROUP BY app_id
                ORDER BY sessions DESC
            """, params)
            apps = [dict(row) for row in cursor.fetchall()]

            # Get app names from apps table if available
            cursor.execute("SELECT app_id, name FROM apps")
            app_names = {row['app_id']: row['name'] for row in cursor.fetchall()}

            for app in apps:
                app['name'] = app_names.get(app['app_id'], app['app_id'])

            return {
                'total_users': user_count,
                'total_sessions': session_stats['total_sessions'],
                'total_runtime_hours': round(session_stats['total_runtime_sec'] / 3600.0, 2),
                'total_crashes': session_stats['total_crashes'],
                'total_events': event_count,
                'apps': apps,
                'filters_applied': {
                    'app_id': app_id,
                    'user': user,
                    'week_id': week_id
                }
            }

    def get_export_data(self, app_id: Optional[str] = None, week_id: Optional[str] = None) -> Dict:
        """Get data for export."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            conditions = []
            params = []

            if app_id:
                conditions.append("app_id = ?")
                params.append(app_id)
            if week_id:
                conditions.append("week_id = ?")
                params.append(week_id)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor.execute(f"SELECT * FROM master_sessions WHERE {where_clause}", params)
            sessions = [dict(row) for row in cursor.fetchall()]

            cursor.execute(f"SELECT * FROM master_events WHERE {where_clause}", params)
            events = [dict(row) for row in cursor.fetchall()]

            cursor.execute(f"SELECT * FROM master_health_checks WHERE {where_clause}", params)
            health_checks = [dict(row) for row in cursor.fetchall()]

            return {
                'sessions': sessions,
                'events': events,
                'health_checks': health_checks
            }

    def get_all_app_stats(self, sort_by: str = "sessions", limit: int = 100) -> List[Dict]:
        """Get usage stats per app."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            order_column = {
                'sessions': 'sessions DESC',
                'runtime': 'runtime_hours DESC',
                'crashes': 'crashes DESC',
                'app_name': 'app_id ASC'
            }.get(sort_by, 'sessions DESC')

            cursor.execute(f"""
                SELECT
                    app_id,
                    COUNT(*) as sessions,
                    COALESCE(SUM(duration_sec), 0) / 3600.0 as runtime_hours,
                    COALESCE(SUM(crash_detected), 0) as crashes,
                    COUNT(DISTINCT machine_id) as unique_machines
                FROM master_sessions
                GROUP BY app_id
                ORDER BY {order_column}
                LIMIT ?
            """, (limit,))
            stats = [dict(row) for row in cursor.fetchall()]

            # Get app names
            cursor.execute("SELECT app_id, name FROM apps")
            app_names = {row['app_id']: row['name'] for row in cursor.fetchall()}

            for stat in stats:
                stat['name'] = app_names.get(stat['app_id'], stat['app_id'])

            return stats

    def get_all_users(self, include_missing: bool = False, limit: int = 100) -> List[Dict]:
        """Get all users who submitted reports."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    user_alias,
                    machine_id,
                    COUNT(*) as submission_count,
                    MIN(started_at) as first_seen,
                    MAX(started_at) as last_seen,
                    COALESCE(SUM(duration_sec), 0) / 3600.0 as total_runtime_hours,
                    COALESCE(SUM(crash_detected), 0) as crash_count
                FROM master_sessions
                WHERE user_alias IS NOT NULL AND user_alias != ''
                GROUP BY user_alias
                ORDER BY last_seen DESC
                LIMIT ?
            """, (limit,))
            users = [dict(row) for row in cursor.fetchall()]

            return users

    def get_weekly_trend(self, weeks: int = 12) -> List[Dict]:
        """Get weekly usage trend."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    week_id,
                    COUNT(*) as sessions,
                    COALESCE(SUM(duration_sec), 0) / 3600.0 as runtime_hours,
                    COALESCE(SUM(crash_detected), 0) as crashes,
                    COUNT(DISTINCT machine_id) as unique_machines,
                    COUNT(DISTINCT user_alias) as unique_users
                FROM master_sessions
                WHERE week_id IS NOT NULL
                GROUP BY week_id
                ORDER BY week_id DESC
                LIMIT ?
            """, (weeks,))

            return [dict(row) for row in cursor.fetchall()]
