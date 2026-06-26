#!/usr/bin/env python3
"""
AppPilotAdmin - Admin tool for importing and analyzing usage reports.

This module serves as the entry point for the PyInstaller-packaged admin application.
"""

import sys
import os
import signal
import socket
import webbrowser
import threading
import time
import logging
from pathlib import Path
import json
import zipfile
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.database import Database
from backend.core.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/admin.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

shutdown_event = threading.Event()


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def find_available_port(start_port: int, max_attempts: int = 100) -> int:
    port = start_port
    for _ in range(max_attempts):
        if not is_port_in_use(port):
            return port
        port += 1
    raise RuntimeError(f"Could not find available port after {max_attempts} attempts")


def open_browser(url: str, delay: float = 1.5) -> None:
    time.sleep(delay)
    try:
        webbrowser.open(url)
        logger.info(f"Opened browser to {url}")
    except Exception as e:
        logger.warning(f"Could not open browser automatically: {e}")


def setup_signal_handlers():
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


class AdminDatabase(Database):
    """Extended database for admin operations with master DB."""

    def __init__(self, db_path: str = "admin/master.db"):
        super().__init__(db_path)

    def initialize(self) -> None:
        """Initialize admin database with additional tables."""
        super().initialize()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS imported_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT NOT NULL,
                    machine_id TEXT,
                    user_alias TEXT,
                    week_id TEXT NOT NULL,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    record_count INTEGER,
                    status TEXT DEFAULT 'success'
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS missing_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_id TEXT NOT NULL,
                    user_alias TEXT,
                    last_week TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            logger.info("Admin database initialized")

    def import_zip(self, zip_path: str) -> dict:
        """Import a weekly export ZIP file into the master database."""
        result = {
            'success': False,
            'filename': Path(zip_path).name,
            'records_imported': 0,
            'message': ''
        }

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                if 'summary.json' in zf.namelist():
                    summary = json.loads(zf.read('summary.json'))
                    result['machine_id'] = summary.get('machine_id')
                    result['user_alias'] = summary.get('user_alias')
                    result['week_id'] = summary.get('week_id')

                if 'sessions.csv' in zf.namelist():
                    sessions = zf.read('sessions.csv').decode('utf-8')
                    result['records_imported'] += self._import_csv('app_sessions', sessions)

                if 'events.csv' in zf.namelist():
                    events = zf.read('events.csv').decode('utf-8')
                    result['records_imported'] += self._import_csv('usage_events', events)

                if 'health_checks.csv' in zf.namelist():
                    health = zf.read('health_checks.csv').decode('utf-8')
                    result['records_imported'] += self._import_csv('health_checks', health)

                if 'process_metrics.csv' in zf.namelist():
                    metrics = zf.read('process_metrics.csv').decode('utf-8')
                    result['records_imported'] += self._import_csv('process_metrics', metrics)

                self.record_import(
                    file_name=result['filename'],
                    machine_id=result.get('machine_id'),
                    user_alias=result.get('user_alias'),
                    week_id=result.get('week_id'),
                    record_count=result['records_imported']
                )

                result['success'] = True
                result['message'] = f"Imported {result['records_imported']} records"

        except Exception as e:
            result['message'] = f"Import failed: {str(e)}"
            logger.error(f"Import failed: {e}")

        return result

    def _import_csv(self, table_name: str, csv_content: str) -> int:
        """Import CSV content into a table."""
        import csv
        from io import StringIO

        count = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()

            reader = csv.DictReader(StringIO(csv_content))
            columns = reader.fieldnames

            for row in reader:
                placeholders = ','.join(['?' for _ in columns])
                columns_sql = ','.join(columns)
                sql = f"INSERT OR IGNORE INTO {table_name} ({columns_sql}) VALUES ({placeholders})"

                try:
                    cursor.execute(sql, [row[col] for col in columns])
                    count += cursor.rowcount
                except Exception as e:
                    logger.debug(f"Skipped row in {table_name}: {e}")

        return count

    def record_import(self, file_name: str, machine_id: str = None,
                      user_alias: str = None, week_id: str = None,
                      record_count: int = 0, status: str = 'success') -> None:
        """Record an import operation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO imported_reports (file_name, machine_id, user_alias, week_id, record_count, status, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (file_name, machine_id, user_alias, week_id, record_count, status, datetime.now()))

    def get_admin_summary(self) -> dict:
        """Get summary stats for admin dashboard."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(DISTINCT machine_id) as count FROM imported_reports")
            total_users = cursor.fetchone()['count']

            cursor.execute("SELECT SUM(record_count) as total FROM imported_reports")
            total_records = cursor.fetchone()['total'] or 0

            cursor.execute("""
                SELECT * FROM imported_reports
                ORDER BY imported_at DESC
                LIMIT 20
            """)
            recent_imports = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT app_id, COUNT(*) as session_count,
                       SUM(duration_sec) as total_runtime,
                       SUM(crash_detected) as crashes
                FROM app_sessions
                GROUP BY app_id
                ORDER BY session_count DESC
                LIMIT 10
            """)
            top_apps = [dict(row) for row in cursor.fetchall()]

            return {
                'total_users': total_users,
                'total_records': total_records,
                'recent_imports': recent_imports,
                'top_apps': top_apps
            }


def create_admin_app():
    """Create the admin FastAPI application."""
    from fastapi import FastAPI, HTTPException, UploadFile, File, Form
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from pathlib import Path

    app = FastAPI(
        title="AppPilot Admin",
        description="Admin dashboard for importing and analyzing usage reports",
        version="1.0.0"
    )

    web_dir = Path(__file__).parent.parent / "web"
    admin_dir = Path(__file__).parent / "admin"
    admin_dir.mkdir(exist_ok=True)

    static_dir = web_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="admin_static")

    if web_dir.exists():
        app.mount("/web", StaticFiles(directory=str(web_dir), html=True), name="admin_web_pages")

    admin_db = AdminDatabase(db_path=str(admin_dir / "master.db"))
    admin_db.initialize()

    @app.get("/", response_class=HTMLResponse)
    async def admin_root():
        html_path = web_dir / "admin_dashboard.html"
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text(encoding='utf-8'), status_code=200)
        return HTMLResponse(content="<h1>AppPilot Admin</h1><p>Dashboard not found.</p>", status_code=200)

    @app.get("/health")
    async def health():
        return {"status": "healthy", "version": "1.0.0", "mode": "admin"}

    @app.get("/api/admin/summary")
    async def get_summary():
        return admin_db.get_admin_summary()

    @app.post("/api/admin/import")
    async def import_report(file: UploadFile = File(...)):
        if not file.filename.endswith('.zip'):
            raise HTTPException(status_code=400, detail="File must be a ZIP file")

        import_dir = admin_dir / "imports"
        import_dir.mkdir(exist_ok=True)

        temp_path = import_dir / file.filename
        with open(temp_path, 'wb') as f:
            content = await file.read()
            f.write(content)

        result = admin_db.import_zip(str(temp_path))
        temp_path.unlink()

        return result

    @app.get("/api/admin/imports")
    async def list_imports():
        with admin_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM imported_reports
                ORDER BY imported_at DESC
                LIMIT 50
            """)
            imports = [dict(row) for row in cursor.fetchall()]
            return {"imports": imports, "total": len(imports)}

    @app.post("/api/admin/report")
    async def generate_report(report_type: str = Form(...), format: str = Form("csv"), days: int = Form(30)):
        from datetime import timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        with admin_db.get_connection() as conn:
            cursor = conn.cursor()

            if report_type == 'summary':
                cursor.execute("""
                    SELECT app_id, COUNT(*) as sessions, SUM(duration_sec) as runtime
                    FROM app_sessions
                    WHERE started_at BETWEEN ? AND ?
                    GROUP BY app_id
                """, (start_date, end_date))
            elif report_type == 'crashes':
                cursor.execute("""
                    SELECT app_id, COUNT(*) as crashes
                    FROM app_sessions
                    WHERE crash_detected = 1 AND started_at BETWEEN ? AND ?
                    GROUP BY app_id
                """, (start_date, end_date))
            else:
                cursor.execute("""
                    SELECT * FROM app_sessions
                    WHERE started_at BETWEEN ? AND ?
                """, (start_date, end_date))

            data = [dict(row) for row in cursor.fetchall()]

        return {
            "success": True,
            "report_type": report_type,
            "format": format,
            "days": days,
            "data": data,
            "record_count": len(data)
        }

    return app


def main():
    """Main entry point for AppPilotAdmin."""
    for dir_name in ['logs', 'data', 'exports', 'admin']:
        Path(dir_name).mkdir(exist_ok=True)

    admin_dir = Path("admin")
    admin_dir.mkdir(exist_ok=True)

    port = 9701

    if is_port_in_use(port):
        logger.warning(f"Port {port} is already in use, attempting to find available port...")
        try:
            port = find_available_port(port)
            logger.info(f"Using port {port} instead")
        except RuntimeError as e:
            logger.error(str(e))
            sys.exit(1)

    app = create_admin_app()

    admin_url = f"http://127.0.0.1:{port}"

    logger.info(f"Starting AppPilotAdmin server on 127.0.0.1:{port}")
    logger.info(f"Admin dashboard: {admin_url}")

    setup_signal_handlers()

    browser_thread = threading.Thread(
        target=open_browser,
        args=(admin_url,),
        daemon=True
    )
    browser_thread.start()

    try:
        import uvicorn

        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        logger.info("AppPilotAdmin shutting down...")
        shutdown_event.set()


if __name__ == "__main__":
    main()