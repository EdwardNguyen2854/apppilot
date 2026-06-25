"""
Utility helper functions for AppPilot.
"""

from datetime import datetime, timedelta
from typing import Optional
import re


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds is None or seconds < 0:
        return "0s"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def format_bytes(bytes_count: int) -> str:
    """Format bytes to human-readable string."""
    if bytes_count is None:
        return "0 B"

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(bytes_count)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def format_timestamp(dt: datetime) -> str:
    """Format datetime to ISO string or relative time."""
    if dt is None:
        return "Never"

    now = datetime.now()
    diff = now - dt

    if diff.total_seconds() < 60:
        return "Just now"
    elif diff.total_seconds() < 3600:
        minutes = int(diff.total_seconds() / 60)
        return f"{minutes}m ago"
    elif diff.total_seconds() < 86400:
        hours = int(diff.total_seconds() / 3600)
        return f"{hours}h ago"
    elif diff.days < 7:
        return f"{diff.days}d ago"
    else:
        return dt.strftime("%Y-%m-%d %H:%M")


def get_week_id(dt: Optional[datetime] = None) -> str:
    """Get ISO week ID for a datetime."""
    if dt is None:
        dt = datetime.now()

    iso_cal = dt.isocalendar()
    return f"{iso_cal[0]}-W{iso_cal[1]:02d}"


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing invalid characters."""
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)
    sanitized = sanitized.strip('. ')
    if len(sanitized) > 200:
        name, ext = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
        max_name = 200 - len(ext) - 1
        sanitized = f"{name[:max_name]}.{ext}" if ext else name[:200]

    return sanitized or "unnamed"


def truncate_string(s: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate a string to maximum length."""
    if len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix


def is_valid_app_id(app_id: str) -> bool:
    """Check if a string is a valid app ID."""
    if not app_id:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', app_id))


def get_app_type_icon(app_type: str) -> str:
    """Get an icon identifier for app type."""
    icons = {
        'desktop': '🖥️', 'web': '🌐', 'api': '⚙️',
        'background': '🔄', 'external': '🔗'
    }
    return icons.get(app_type.lower(), '📦')


def calculate_percentage(part: float, total: float) -> float:
    """Calculate percentage, handling division by zero."""
    if total == 0:
        return 0.0
    return round((part / total) * 100, 1)