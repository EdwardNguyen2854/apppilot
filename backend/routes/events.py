"""
Events API routes for AppPilot.

Provides endpoint for receiving usage events from apps.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/events", tags=["events"])


class UsageEvent(BaseModel):
    """Usage event payload from apps."""
    app_id: str
    event: str = Field(..., description="Event name (e.g., 'file_opened', 'tool_called')")
    details: Optional[Dict[str, Any]] = None
    success: bool = True
    app_version: Optional[str] = None


VALID_EVENTS = {
    'app_opened', 'file_opened', 'folder_opened', 'search_used',
    'export_clicked', 'export_success', 'export_failed', 'api_called',
    'tool_called', 'tool_success', 'tool_failed', 'error_happened',
    'feature_used', 'button_clicked', 'settings_changed',
    'session_started', 'session_ended', 'web_api_called', 'mcp_tool_called',
    'cli_tool_run'
}


def init_events_router(database, config):
    """Initialize router with dependencies."""

    @router.post("")
    async def receive_event(event: UsageEvent):
        """Receive a usage event from an app."""
        if event.event not in VALID_EVENTS:
            logger.warning(f"Unknown event type received: {event.event}")

        clean_details = _sanitize_details(event.details) if event.details else None

        try:
            database.record_usage_event(
                app_id=event.app_id,
                event_name=event.event,
                details=clean_details,
                success=event.success,
                app_version=event.app_version,
                machine_id=config.get_machine_id(),
                user_alias=config.get_user_alias()
            )

            logger.debug(f"Recorded event: {event.app_id}/{event.event}")

            return {
                "success": True,
                "message": f"Event {event.event} recorded for {event.app_id}"
            }

        except Exception as e:
            logger.error(f"Failed to record event: {e}")
            return {
                "success": False,
                "message": str(e)
            }

    @router.get("/types")
    async def get_event_types():
        """Get list of valid event types."""
        return {
            "events": list(VALID_EVENTS),
            "total": len(VALID_EVENTS)
        }

    return router


def _sanitize_details(details: Dict) -> Dict:
    """Sanitize event details to remove potentially sensitive information."""
    if not details:
        return None

    sanitized = {}
    sensitive_keys = {
        'path', 'filepath', 'full_path', 'filename', 'customer',
        'name', 'email', 'phone', 'address', 'content', 'data',
        'token', 'key', 'password', 'secret', 'body', 'text'
    }

    for key, value in details.items():
        key_lower = key.lower()

        if any(s in key_lower for s in sensitive_keys):
            sanitized[key] = "[redacted]"
            continue

        if isinstance(value, str) and len(value) > 500:
            sanitized[key] = value[:500] + "...[truncated]"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_details(value)
        elif isinstance(value, list):
            sanitized[key] = [
                _sanitize_details(item) if isinstance(item, dict) else item
                for item in value[:50]
            ]
        else:
            sanitized[key] = value

    return sanitized
