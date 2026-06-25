"""
Apps API routes for AppPilot.

Provides endpoints for:
- Listing all apps
- Getting app status
- Starting/stopping/restarting apps
- Getting app logs
- MCP server discovery and lifecycle
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Optional, Dict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/apps", tags=["apps"])


def _get_mcp_status(mcp_manager, app_id):
    if mcp_manager is None:
        return None
    return mcp_manager.get_status(app_id)


def _is_mcp_app(app_config):
    return app_config and app_config.get("type") == "mcp"


def init_apps_router(process_manager, database, config, monitor, mcp_manager=None):
    """Initialize router with dependencies."""

    @router.get("/config")
    async def get_config():
        """Get current configuration including machine_id, user_alias, hostname."""
        import socket
        machine_id = config.get_machine_id() if config else 'unknown'
        user_alias = config.get_user_alias() if config else 'unknown'
        hostname = socket.gethostname()

        db_size = 'unknown'
        try:
            db_path = Path('data/usage.db')
            if db_path.exists():
                size_bytes = db_path.stat().st_size
                if size_bytes < 1024 * 1024:
                    db_size = f"~{(size_bytes / 1024):.1f} KB"
                else:
                    db_size = f"~{(size_bytes / (1024 * 1024)):.1f} MB"
        except Exception:
            pass

        return {
            "machine_id": machine_id,
            "user_alias": user_alias,
            "hostname": hostname,
            "app_version": "1.0.0",
            "db_size": db_size
        }

    @router.get("")
    async def list_apps():
        """Get all configured apps."""
        apps = config.get_apps()
        result = []

        for app in apps:
            app_id = app.get('id')
            status = process_manager.get_process_status(app_id)
            health_status = monitor.get_last_health_status(app_id)

            app_info = {
                'id': app_id,
                'name': app.get('name'),
                'type': app.get('type'),
                'description': app.get('description', ''),
                'port': app.get('port'),
                'url': app.get('url'),
                'running': status.get('running', False),
                'status': 'online' if status.get('running') else 'offline',
                'pid': status.get('pid'),
                'cpu_percent': status.get('cpu_percent'),
                'memory_mb': status.get('memory_mb'),
                'uptime_sec': status.get('uptime_sec'),
                'auto_start': app.get('auto_start', False),
                'health_url': app.get('health_url'),
                'health_status': health_status.get('status') if health_status else None,
            }

            if _is_mcp_app(app):
                mcp_status = _get_mcp_status(mcp_manager, app_id)
                if mcp_status:
                    app_info['mcp_status'] = mcp_status['status']
                    app_info['tool_count'] = mcp_status['tool_count']
                else:
                    app_info['mcp_status'] = 'disconnected'
                    app_info['tool_count'] = 0

            result.append(app_info)

        return {"apps": result, "total": len(result)}

    @router.get("/{app_id}/status")
    async def get_app_status(app_id: str):
        """Get detailed status of a specific app."""
        app_config = config.get_app_by_id(app_id)
        if not app_config:
            raise HTTPException(status_code=404, detail=f"App {app_id} not found")

        status = process_manager.get_process_status(app_id)
        health_status = monitor.get_last_health_status(app_id)

        port_open = None
        if app_config.get('port'):
            port_open = process_manager.is_port_in_use(app_config['port'])

        message = "Running" if status.get('running') else "Not running"
        if status.get('running') and health_status:
            if health_status.get('status') == 'healthy':
                message = "Healthy"
            elif health_status.get('status') != 'unknown':
                message = f"Health check: {health_status.get('status')}"

        result = {
            'app_id': app_id,
            'name': app_config.get('name', app_id),
            'type': app_config.get('type', 'unknown'),
            'running': status.get('running', False),
            'status': message,
            'pid': status.get('pid'),
            'cpu_percent': status.get('cpu_percent'),
            'memory_mb': status.get('memory_mb'),
            'uptime_sec': status.get('uptime_sec'),
            'port_open': port_open,
            'health_status': health_status.get('status') if health_status else None,
            'message': message
        }

        if _is_mcp_app(app_config):
            mcp_status = _get_mcp_status(mcp_manager, app_id)
            if mcp_status:
                result['mcp_status'] = mcp_status['status']
                result['tool_count'] = mcp_status['tool_count']
            else:
                result['mcp_status'] = 'disconnected'
                result['tool_count'] = 0

        return result

    @router.post("/{app_id}/start")
    async def start_app(app_id: str, background_tasks: BackgroundTasks):
        """Start an app."""
        app_config = config.get_app_by_id(app_id)
        if not app_config:
            raise HTTPException(status_code=404, detail=f"App {app_id} not found")

        if process_manager.is_process_running(app_id):
            return {"success": False, "message": f"App {app_id} is already running"}

        if _is_mcp_app(app_config):
            return await _start_mcp_app(app_id, app_config)
        else:
            return await _start_regular_app(app_id, app_config)

    async def _start_mcp_app(app_id: str, app_config: Dict):
        from backend.core.mcp_client import MCPManager

        try:
            if mcp_manager is None:
                raise RuntimeError("MCP manager not available")

            exe_path = app_config.get('exe', '')
            args = app_config.get('args', [])

            client = await mcp_manager.connect(app_id, app_config)

            database.register_app(app_config)
            session_id = database.start_session(
                app_id=app_id,
                machine_id=config.get_machine_id(),
                user_alias=config.get_user_alias(),
                app_version=app_config.get('version')
            )

            logger.info(f"Started MCP app {app_id} with {len(client.tools)} tools")

            return {
                "success": True,
                "message": f"Started MCP app {app_id}",
                "app_id": app_id,
                "tool_count": len(client.tools),
                "mcp_status": client.status,
            }
        except Exception as e:
            logger.warning(f"Failed to start MCP app {app_id}: {e}")
            return {"success": False, "message": str(e), "app_id": app_id}

    async def _start_regular_app(app_id: str, app_config: Dict):
        exe_path = app_config.get('exe', '')
        args = app_config.get('args', [])
        log_file = app_config.get('log_file')

        success, message = process_manager.start_process(
            app_id=app_id,
            exe_path=exe_path,
            args=args,
            log_file=log_file
        )

        if success:
            database.register_app(app_config)
            database.start_session(
                app_id=app_id,
                machine_id=config.get_machine_id(),
                user_alias=config.get_user_alias(),
                app_version=app_config.get('version')
            )

            if app_config.get('monitor', {}).get('process') or app_config.get('monitor', {}).get('cpu_ram'):
                monitor.start_monitoring(app_config, interval=10)

            logger.info(f"Started app {app_id}")
        else:
            logger.warning(f"Failed to start app {app_id}: {message}")

        return {"success": success, "message": message, "app_id": app_id}

    @router.post("/{app_id}/stop")
    async def stop_app(app_id: str):
        """Stop an app."""
        app_config = config.get_app_by_id(app_id)
        if not app_config:
            raise HTTPException(status_code=404, detail=f"App {app_id} not found")

        if _is_mcp_app(app_config):
            return await _stop_mcp_app(app_id)
        else:
            return await _stop_regular_app(app_id)

    async def _stop_mcp_app(app_id: str):
        try:
            if mcp_manager:
                await mcp_manager.disconnect(app_id)

            active_session = database.get_active_session(app_id)
            if active_session:
                database.end_session(active_session['id'], exit_code=0, crash_detected=False)

            logger.info(f"Stopped MCP app {app_id}")
            return {"success": True, "message": f"Stopped MCP app {app_id}", "app_id": app_id}
        except Exception as e:
            logger.warning(f"Failed to stop MCP app {app_id}: {e}")
            return {"success": False, "message": str(e), "app_id": app_id}

    async def _stop_regular_app(app_id: str):
        if not process_manager.is_process_running(app_id):
            return {"success": False, "message": f"App {app_id} is not running"}

        success, message = process_manager.stop_process(app_id)

        if success:
            active_session = database.get_active_session(app_id)
            if active_session:
                database.end_session(active_session['id'], exit_code=0, crash_detected=False)
            logger.info(f"Stopped app {app_id}")
        else:
            logger.warning(f"Failed to stop app {app_id}: {message}")

        return {"success": success, "message": message, "app_id": app_id}

    @router.post("/{app_id}/restart")
    async def restart_app(app_id: str):
        """Restart an app."""
        app_config = config.get_app_by_id(app_id)
        if not app_config:
            raise HTTPException(status_code=404, detail=f"App {app_id} not found")

        active_session = database.get_active_session(app_id)

        exe_path = app_config.get('exe', '')
        args = app_config.get('args', [])
        log_file = app_config.get('log_file')

        success, message = process_manager.restart_process(
            app_id=app_id,
            exe_path=exe_path,
            args=args,
            log_file=log_file
        )

        if success:
            if active_session:
                database.end_session(active_session['id'], exit_code=-1, crash_detected=True)

            database.start_session(
                app_id=app_id,
                machine_id=config.get_machine_id(),
                user_alias=config.get_user_alias(),
                app_version=app_config.get('version')
            )

            logger.info(f"Restarted app {app_id}")
        else:
            logger.warning(f"Failed to restart app {app_id}: {message}")

        return {"success": success, "message": message, "app_id": app_id}

    @router.get("/{app_id}/logs")
    async def get_app_logs(app_id: str, lines: int = 100):
        """Get recent log entries for an app."""
        logs = process_manager.read_logs(app_id, lines=lines)
        return {
            "app_id": app_id,
            "logs": logs,
            "total_lines": len(logs)
        }

    @router.get("/{app_id}/sessions")
    async def get_app_sessions(app_id: str, limit: int = 50):
        """Get session history for an app."""
        sessions = database.get_app_sessions(app_id, limit=limit)
        return {"app_id": app_id, "sessions": sessions, "total": len(sessions)}

    @router.get("/{app_id}/mcp/status")
    async def get_mcp_status(app_id: str):
        """Get MCP connection status for an MCP server app."""
        app_config = config.get_app_by_id(app_id)
        if not app_config:
            raise HTTPException(status_code=404, detail=f"App {app_id} not found")
        if not _is_mcp_app(app_config):
            raise HTTPException(status_code=400, detail=f"App {app_id} is not an MCP app")

        status = _get_mcp_status(mcp_manager, app_id)
        return {
            "status": status["status"] if status else "disconnected",
            "tool_count": status["tool_count"] if status else 0,
            "resource_count": status["resource_count"] if status else 0,
            "prompt_count": status["prompt_count"] if status else 0,
            "initialized_at": status["initialized_at"] if status else None,
            "error_message": status["error_message"] if status else None,
        }

    @router.get("/{app_id}/mcp/tools")
    async def get_mcp_tools(app_id: str):
        """Get discovered tools for an MCP server."""
        app_config = config.get_app_by_id(app_id)
        if not app_config:
            raise HTTPException(status_code=404, detail=f"App {app_id} not found")
        if not _is_mcp_app(app_config):
            raise HTTPException(status_code=400, detail=f"App {app_id} is not an MCP app")

        if mcp_manager is None:
            raise HTTPException(status_code=500, detail="MCP manager not available")

        client = mcp_manager.get_client(app_id)
        if client is None or client.status == "disconnected":
            raise HTTPException(status_code=400, detail="MCP server is not running")

        return {"tools": client.tools, "count": len(client.tools)}

    @router.get("/{app_id}/mcp/resources")
    async def get_mcp_resources(app_id: str):
        """Get discovered resources for an MCP server."""
        app_config = config.get_app_by_id(app_id)
        if not app_config:
            raise HTTPException(status_code=404, detail=f"App {app_id} not found")
        if not _is_mcp_app(app_config):
            raise HTTPException(status_code=400, detail=f"App {app_id} is not an MCP app")

        if mcp_manager is None:
            raise HTTPException(status_code=500, detail="MCP manager not available")

        client = mcp_manager.get_client(app_id)
        if client is None or client.status == "disconnected":
            raise HTTPException(status_code=400, detail="MCP server is not running")

        return {"resources": client.resources, "count": len(client.resources)}

    @router.get("/{app_id}/mcp/prompts")
    async def get_mcp_prompts(app_id: str):
        """Get discovered prompts for an MCP server."""
        app_config = config.get_app_by_id(app_id)
        if not app_config:
            raise HTTPException(status_code=404, detail=f"App {app_id} not found")
        if not _is_mcp_app(app_config):
            raise HTTPException(status_code=400, detail=f"App {app_id} is not an MCP app")

        if mcp_manager is None:
            raise HTTPException(status_code=500, detail="MCP manager not available")

        client = mcp_manager.get_client(app_id)
        if client is None or client.status == "disconnected":
            raise HTTPException(status_code=400, detail="MCP server is not running")

        return {"prompts": client.prompts, "count": len(client.prompts)}

    return router