"""
Usage API routes for AppPilot.

Provides endpoints for:
- Getting usage summary
- Exporting weekly reports
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
import json
import zipfile
import csv
from io import StringIO
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/usage", tags=["usage"])


def init_usage_router(database, config):
    """Initialize router with dependencies."""

    @router.get("/summary")
    async def get_usage_summary(days: int = 7):
        """Get usage summary for the specified number of days."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        summary = database.get_usage_summary(start_date, end_date)

        total_sessions = sum(s['session_count'] for s in summary.get('sessions', []))
        total_runtime = sum(s.get('total_runtime', 0) or 0 for s in summary.get('sessions', []))
        total_crashes = sum(s.get('crash_count', 0) for s in summary.get('sessions', []))
        total_events = sum(e['event_count'] for e in summary.get('events', []))

        return {
            'period': {
                'start': summary['start_date'],
                'end': summary['end_date'],
                'days': days
            },
            'totals': {
                'sessions': total_sessions,
                'runtime_sec': total_runtime,
                'crashes': total_crashes,
                'events': total_events
            },
            'by_app': summary.get('sessions', []),
            'events_by_app': summary.get('events', [])
        }

    @router.post("/export-weekly")
    async def export_weekly(year: int = None, week: int = None):
        """Export weekly usage data to a ZIP file."""
        if year is None or week is None:
            now = datetime.now()
            year, week, _ = now.isocalendar()

        exports_dir = Path(config.get('exports_dir', 'exports'))
        exports_dir.mkdir(parents=True, exist_ok=True)

        machine_id = config.get_machine_id()

        data = database.get_weekly_export_data(year, week)

        if not data['sessions'] and not data['events']:
            return {
                "success": False,
                "message": f"No data found for {year}-W{week:02d}"
            }

        filename = f"usage_{year}-W{week:02d}_{machine_id}.zip"
        filepath = exports_dir / filename

        with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
            summary_json = {
                'week_id': data['week_id'],
                'generated_at': data['generated_at'],
                'machine_id': machine_id,
                'user_alias': config.get_user_alias(),
                'app_versions': data['app_versions'],
                'session_count': len(data['sessions']),
                'event_count': len(data['events']),
                'health_check_count': len(data['health_checks']),
                'metrics_count': len(data['process_metrics'])
            }
            zf.writestr('summary.json', json.dumps(summary_json, indent=2))

            if data['events']:
                events_io = StringIO()
                writer = csv.DictWriter(events_io, fieldnames=data['events'][0].keys())
                writer.writeheader()
                writer.writerows(data['events'])
                zf.writestr('events.csv', events_io.getvalue())

            if data['sessions']:
                sessions_io = StringIO()
                writer = csv.DictWriter(sessions_io, fieldnames=data['sessions'][0].keys())
                writer.writeheader()
                writer.writerows(data['sessions'])
                zf.writestr('sessions.csv', sessions_io.getvalue())

            if data['health_checks']:
                health_io = StringIO()
                writer = csv.DictWriter(health_io, fieldnames=data['health_checks'][0].keys())
                writer.writeheader()
                writer.writerows(data['health_checks'])
                zf.writestr('health_checks.csv', health_io.getvalue())

            if data['process_metrics']:
                metrics_io = StringIO()
                writer = csv.DictWriter(metrics_io, fieldnames=data['process_metrics'][0].keys())
                writer.writeheader()
                writer.writerows(data['process_metrics'])
                zf.writestr('process_metrics.csv', metrics_io.getvalue())

        total_records = (len(data['sessions']) + len(data['events']) +
                        len(data['health_checks']) + len(data['process_metrics']))
        database.record_export(
            week_id=data['week_id'],
            file_name=filename,
            record_count=total_records,
            status='completed'
        )

        logger.info(f"Exported weekly data to {filepath}")

        return {
            "success": True,
            "message": f"Exported to {filename}",
            "filename": filename,
            "filepath": str(filepath),
            "records": total_records
        }

    @router.get("/exports")
    async def list_exports():
        """List all exports."""
        exports_dir = Path(config.get('exports_dir', 'exports'))
        if not exports_dir.exists():
            return {"exports": [], "total": 0}

        exports = []
        for f in sorted(exports_dir.glob("usage_*.zip"), reverse=True):
            stat = f.stat()
            exports.append({
                'filename': f.name,
                'size_bytes': stat.st_size,
                'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat()
            })

        return {"exports": exports, "total": len(exports)}

    @router.get("/sessions")
    async def get_all_sessions(limit: int = 100, offset: int = 0):
        """Get all sessions with pagination."""
        with database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM app_sessions
                ORDER BY started_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            sessions = [dict(row) for row in cursor.fetchall()]

            cursor.execute("SELECT COUNT(*) as total FROM app_sessions")
            total = cursor.fetchone()['total']

            return {"sessions": sessions, "total": total, "limit": limit, "offset": offset}

    @router.get("/events")
    async def get_all_events(app_id: str = None, limit: int = 100, offset: int = 0):
        """Get usage events with optional app filter."""
        with database.get_connection() as conn:
            cursor = conn.cursor()

            if app_id:
                cursor.execute("""
                    SELECT * FROM usage_events
                    WHERE app_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """, (app_id, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM usage_events
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))

            events = [dict(row) for row in cursor.fetchall()]

            if app_id:
                cursor.execute("SELECT COUNT(*) as total FROM usage_events WHERE app_id = ?", (app_id,))
            else:
                cursor.execute("SELECT COUNT(*) as total FROM usage_events")
            total = cursor.fetchone()['total']

            return {"events": events, "total": total, "limit": limit, "offset": offset}

    @router.delete("/data")
    async def clear_old_data(days: int = 90):
        """Delete usage data older than specified days."""
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=days)

        deleted = database.clear_old_usage_data(cutoff_date)

        logger.info(f"Cleared {deleted} old usage records (older than {days} days)")

        return {
            "deleted": deleted,
            "message": f"Old data cleaned up ({days} days threshold)"
        }

    @router.post("/reset")
    async def reset_database():
        """Reset (clear) all usage data from the database."""
        deleted = database.reset_usage_data()

        logger.warning("Database reset requested")

        return {
            "success": True,
            "message": "Database reset complete",
            "deleted": deleted
        }

    return router