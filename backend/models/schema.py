"""
Pydantic schemas for AppPilot API.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime


class AppConfig(BaseModel):
    """App configuration schema."""
    id: str
    name: str
    type: str
    description: Optional[str] = ""
    exe: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    port: Optional[int] = None
    url: Optional[str] = None
    health_url: Optional[str] = None
    auto_start: bool = False
    log_file: Optional[str] = None
    monitor: Dict[str, bool] = Field(default_factory=lambda: {
        'process': True, 'port': True, 'http': True, 'cpu_ram': True, 'events': True
    })


class AppStatus(BaseModel):
    """App status schema."""
    app_id: str
    name: str
    type: str
    running: bool
    status: str
    pid: Optional[int] = None
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None
    uptime_sec: Optional[int] = None
    port_open: Optional[bool] = None
    health_status: Optional[str] = None
    message: str


class UsageEvent(BaseModel):
    """Usage event schema."""
    app_id: str
    event: str
    details: Optional[Dict[str, Any]] = None
    success: bool = True
    app_version: Optional[str] = None


class SessionInfo(BaseModel):
    """Session information schema."""
    id: int
    app_id: str
    machine_id: str
    user_alias: Optional[str]
    started_at: datetime
    stopped_at: Optional[datetime] = None
    duration_sec: Optional[int] = None
    exit_code: Optional[int] = None
    crash_detected: bool = False
    app_version: Optional[str] = None


class ProcessMetric(BaseModel):
    """Process metric schema."""
    id: int
    app_id: str
    timestamp: datetime
    cpu_percent: float
    memory_mb: float
    process_id: Optional[int] = None


class HealthCheckResult(BaseModel):
    """Health check result schema."""
    id: int
    app_id: str
    timestamp: datetime
    port: Optional[int] = None
    status: str
    response_ms: Optional[int] = None
    error_message: Optional[str] = None


class ExportInfo(BaseModel):
    """Export information schema."""
    id: int
    week_id: str
    exported_at: datetime
    file_name: str
    record_count: int
    status: str


class UsageSummary(BaseModel):
    """Usage summary schema."""
    period: Dict[str, str]
    totals: Dict[str, int]
    by_app: List[Dict]
    events_by_app: List[Dict]


class HealthStatusResponse(BaseModel):
    """Health check status response."""
    status: str
    timestamp: str
    version: str
    uptime_seconds: int
    apps_total: int
    apps_running: int


class MCPTool(BaseModel):
    """MCP tool definition."""
    name: str
    description: Optional[str] = None
    inputSchema: Optional[Dict[str, Any]] = None


class MCPResource(BaseModel):
    """MCP resource definition."""
    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = None


class MCPPrompt(BaseModel):
    """MCP prompt definition."""
    name: str
    description: Optional[str] = None
    arguments: Optional[List[Dict[str, Any]]] = None


class MCPStatusResponse(BaseModel):
    """MCP connection status."""
    status: str
    tool_count: int = 0
    resource_count: int = 0
    prompt_count: int = 0
    initialized_at: Optional[str] = None
    error_message: Optional[str] = None