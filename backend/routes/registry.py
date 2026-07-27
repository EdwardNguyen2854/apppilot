"""Registry reload, discovery, and dummy-tool management endpoints."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.core.app_registry import AppRegistryService, SUPPORTED_DUMMY_TYPES


logger = logging.getLogger(__name__)


def init_registry_router(process_manager, config, mcp_manager=None, database=None, monitor=None):
    router = APIRouter(prefix="/api/registry", tags=["registry"])

    def service():
        return AppRegistryService(config)

    @router.post("/reload")
    async def reload_registry():
        try:
            before = {app.get("id") for app in config.get_apps()}
            config.reload()
            after = {app.get("id") for app in config.get_apps()}
            removed = before - after
            for app_id in removed:
                if mcp_manager and mcp_manager.get_client(app_id):
                    await mcp_manager.disconnect(app_id)
                if process_manager.is_process_running(app_id):
                    process_manager.stop_process(app_id, force=True)
                if monitor:
                    monitor.stop_monitoring(app_id)
                if database:
                    active_session = database.get_active_session(app_id)
                    if active_session:
                        database.end_session(active_session['id'], exit_code=0, crash_detected=False)
            return {
                "success": True,
                "total": len(after),
                "added": sorted(after - before),
                "removed": sorted(removed),
                "message": f"Reloaded {len(after)} apps from apps.json",
            }
        except Exception as exc:
            logger.warning("Registry reload failed: %s", exc)
            raise HTTPException(status_code=400, detail=f"Could not reload apps.json: {exc}")

    @router.get("/discover")
    async def discover_apps():
        try:
            suggestions = service().discover()
            return {"suggestions": suggestions, "total": len(suggestions)}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/register")
    async def register_discovered_app(payload: Dict[str, Any]):
        try:
            app = service().validate_suggestion(payload)
            config.add_app(app)
            return {"success": True, "app": app, "message": f"Registered {app['name']}"}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/dummy")
    async def create_dummy_tool(payload: Dict[str, Any]):
        app_type = payload.get("type")
        if app_type not in SUPPORTED_DUMMY_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Type must be one of: {', '.join(sorted(SUPPORTED_DUMMY_TYPES))}",
            )
        try:
            app = service().create_dummy(app_type)
            return {"success": True, "app": app, "message": f"Added {app['name']}"}
        except Exception as exc:
            logger.warning("Dummy creation failed: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc))

    @router.delete("/dummy")
    async def remove_all_dummy_tools():
        registry = service()
        dummy_ids = registry.dummy_ids()
        for app_id in dummy_ids:
            if mcp_manager and mcp_manager.get_client(app_id):
                await mcp_manager.disconnect(app_id)
            if process_manager.is_process_running(app_id):
                process_manager.stop_process(app_id, force=True)

        try:
            removed_apps = config.remove_apps(dummy_ids)
            removed_folders = registry.remove_dummy_files(removed_apps)
            return {
                "success": True,
                "removed": len(removed_apps),
                "removed_folders": removed_folders,
                "message": f"Removed {len(removed_apps)} dummy tools",
            }
        except Exception as exc:
            logger.warning("Dummy removal failed: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc))

    return router
