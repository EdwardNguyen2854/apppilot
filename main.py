#!/usr/bin/env python3
"""
AppPilot Main Entry Point

This module serves as the entry point for the PyInstaller-packaged AppPilot application.
It handles:
- Starting the web server
- Opening the browser to the dashboard
- Graceful shutdown handling
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

# Add the backend directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from backend.app import create_app
from backend.core.config import Config
from backend.core.database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/apppilot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global shutdown flag
shutdown_event = threading.Event()


def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def find_available_port(start_port: int, max_attempts: int = 100) -> int:
    """Find an available port starting from start_port."""
    port = start_port
    for _ in range(max_attempts):
        if not is_port_in_use(port):
            return port
        port += 1
    raise RuntimeError(f"Could not find available port after {max_attempts} attempts")


def open_browser(url: str, delay: float = 1.5) -> None:
    """Open the browser to the specified URL after a short delay."""
    time.sleep(delay)
    try:
        webbrowser.open(url)
        logger.info(f"Opened browser to {url}")
    except Exception as e:
        logger.warning(f"Could not open browser automatically: {e}")


def setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def get_local_ip() -> str:
    """Get the local machine IP address."""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        return local_ip
    except Exception:
        return "127.0.0.1"


def main():
    """Main entry point for AppPilot."""
    # Ensure required directories exist
    dirs_to_create = ['logs', 'data', 'exports', 'apps']
    for dir_name in dirs_to_create:
        Path(dir_name).mkdir(exist_ok=True)

    # Load configuration
    config = Config()
    port = config.get('port', 9700)
    host = config.get('host', '127.0.0.1')

    # Check if port is in use, find alternative if needed
    if is_port_in_use(port):
        logger.warning(f"Port {port} is already in use, attempting to find available port...")
        try:
            port = find_available_port(port)
            logger.info(f"Using port {port} instead")
        except RuntimeError as e:
            logger.error(str(e))
            sys.exit(1)

    # Initialize database
    db = Database()
    db.initialize()
    logger.info("Database initialized")

    # Create FastAPI application
    app = create_app(config, db)

    # Construct URLs
    main_url = f"http://{host}:{port}"
    admin_url = f"http://{host}:{port + 1}"

    logger.info(f"Starting AppPilot server on {host}:{port}")
    logger.info(f"Main dashboard: {main_url}")
    logger.info(f"Admin dashboard: {admin_url}")

    # Setup signal handlers for graceful shutdown
    setup_signal_handlers()

    # Start browser opener in a separate thread
    browser_thread = threading.Thread(
        target=open_browser,
        args=(main_url,),
        daemon=True
    )
    browser_thread.start()

    try:
        # Import and run uvicorn
        import uvicorn

        # Run the server
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        logger.info("AppPilot shutting down...")
        shutdown_event.set()


if __name__ == "__main__":
    main()