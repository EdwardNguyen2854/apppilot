"""
FastAPI Application Factory for AppPilot.

Creates and configures the FastAPI application with all routes and middleware.
"""

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/apppilot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    logger.info("AppPilot starting up...")
    yield
    logger.info("AppPilot shutting down...")
    if hasattr(app.state, 'mcp_manager'):
        await app.state.mcp_manager.disconnect_all()
    if hasattr(app.state, 'monitor'):
        app.state.monitor.stop_all_monitoring()


def create_app(config=None, database=None):
    """Create and configure the FastAPI application."""
    from backend.core.process_manager import ProcessManager
    from backend.core.monitor import Monitor
    from backend.core.mcp_client import MCPManager
    from backend.routes import apps_router, usage_router, events_router, admin_router, init_apps_router, init_usage_router, init_events_router, init_admin_router

    app = FastAPI(
        title="AppPilot",
        description="Local web app for launching, monitoring, and collecting usage data from internal EXE-based tools.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )

    app.state.config = config
    app.state.database = database

    process_manager = ProcessManager()
    monitor = Monitor(process_manager, database)
    mcp_manager = MCPManager()

    app.state.process_manager = process_manager
    app.state.monitor = monitor
    app.state.mcp_manager = mcp_manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:9700", "http://localhost:9700", "http://127.0.0.1:9701"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    template_dir = Path(__file__).parent.parent / "web"
    templates = Jinja2Templates(directory=str(template_dir))

    static_dir = template_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    apps_router_configured = init_apps_router(process_manager, database, config, monitor, mcp_manager)
    usage_router_configured = init_usage_router(database, config)
    events_router_configured = init_events_router(database, config)
    admin_router_configured = init_admin_router(database, config)

    app.include_router(apps_router_configured)
    app.include_router(usage_router_configured)
    app.include_router(events_router_configured)
    app.include_router(admin_router_configured)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "message": str(exc)}
        )

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Redirect root to the web dashboard."""
        html_path = Path(__file__).parent.parent / "web" / "index.html"
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text(encoding='utf-8'), status_code=200)
        return HTMLResponse(content="<h1>AppPilot is running</h1><p>Web dashboard not found.</p>", status_code=200)

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        apps = config.get_apps() if config else []
        running_count = sum(1 for app in apps if process_manager.is_process_running(app.get('id', '')))

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "uptime_seconds": int(time.time() - start_time),
            "apps_total": len(apps),
            "apps_running": running_count
        }

    @app.get("/api")
    async def api_info():
        """API information endpoint."""
        return {
            "name": "AppPilot API",
            "version": "1.0.0",
            "endpoints": {
                "apps": "/api/apps",
                "usage": "/api/usage",
                "events": "/api/events"
            }
        }

    @app.get("/api/system/stats")
    async def system_stats():
        """Get system resource statistics."""
        return process_manager.get_system_stats()

    @app.get("/api/config")
    async def get_config():
        """Get current configuration including machine_id, user_alias, hostname, db_size."""
        import socket
        machine_id = config.get_machine_id() if config else 'unknown'
        user_alias = config.get_user_alias() if config else 'unknown'
        hostname = socket.gethostname()

        # Get DB size
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

    @app.on_event("startup")
    async def auto_start_apps():
        """Auto-start apps that have auto_start enabled."""
        if config is None:
            return

        logger.info("Checking for auto-start apps...")
        apps = config.get_apps()

        fastapi_app = app

        for app_entry in apps:
            if app_entry.get('auto_start', False):
                app_id = app_entry.get('id')
                if not process_manager.is_process_running(app_id):

                    if app_entry.get('type') == 'mcp':
                        logger.info(f"Auto-starting MCP app {app_id}...")
                        try:
                            mcp_manager = fastapi_app.state.mcp_manager
                            if mcp_manager:
                                client = await mcp_manager.connect(app_id, app_entry)
                                database.register_app(app_entry)
                                database.start_session(
                                    app_id=app_id,
                                    machine_id=config.get_machine_id(),
                                    user_alias=config.get_user_alias(),
                                    app_version=app_entry.get('version')
                                )
                                logger.info(f"Auto-started MCP app {app_id} with {len(client.tools)} tools")
                        except Exception as e:
                            logger.warning(f"Failed to auto-start MCP app {app_id}: {e}")
                    else:
                        exe_path = app_entry.get('exe', '')
                        args = app_entry.get('args', [])
                        log_file = app_entry.get('log_file')

                        logger.info(f"Auto-starting {app_id}...")
                        success, message = process_manager.start_process(
                            app_id=app_id,
                            exe_path=exe_path,
                            args=args,
                            log_file=log_file
                        )

                        if success:
                            database.register_app(app_entry)
                            database.start_session(
                                app_id=app_id,
                                machine_id=config.get_machine_id(),
                                user_alias=config.get_user_alias(),
                                app_version=app_entry.get('version')
                            )
                            monitor.start_monitoring(app_entry, interval=10)

        logger.info("AppPilot startup complete")

    return app