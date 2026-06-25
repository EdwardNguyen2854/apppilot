"""
Monitor Engine for AppPilot.

Handles continuous monitoring of:
- Process status
- Port availability
- HTTP health checks
- CPU/RAM usage
"""

import asyncio
import logging
import time
import socket
from typing import Dict, Optional
from datetime import datetime
import httpx
import psutil

logger = logging.getLogger(__name__)


class Monitor:
    """Monitoring engine for AppPilot apps."""

    def __init__(self, process_manager, database):
        self.process_manager = process_manager
        self.database = database
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._last_health_status: Dict[str, Dict] = {}
        self._running = False
        logger.info("Monitor initialized")

    async def check_port(self, app_id: str, port: int) -> Dict:
        """Check if a port is open and accepting connections."""
        start_time = time.time()
        result = {
            'app_id': app_id,
            'port': port,
            'open': False,
            'response_time_ms': None,
            'error': None
        }

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('127.0.0.1', port),
                timeout=5.0
            )
            writer.close()
            await writer.wait_closed()

            result['open'] = True
            result['response_time_ms'] = int((time.time() - start_time) * 1000)
            logger.debug(f"Port {port} for {app_id} is open")

        except asyncio.TimeoutError:
            result['error'] = 'Connection timeout'
        except ConnectionRefusedError:
            result['error'] = 'Connection refused'
        except Exception as e:
            result['error'] = str(e)

        return result

    async def check_http_health(self, app_id: str, health_url: str) -> Dict:
        """Check HTTP health endpoint."""
        start_time = time.time()
        result = {
            'app_id': app_id,
            'url': health_url,
            'status': 'unknown',
            'response_ms': None,
            'status_code': None,
            'error': None
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(health_url)

                result['status_code'] = response.status_code
                result['response_ms'] = int((time.time() - start_time) * 1000)

                if response.status_code == 200:
                    result['status'] = 'healthy'
                else:
                    result['status'] = f'unhealthy_code_{response.status_code}'

                logger.debug(f"Health check for {app_id}: {result['status']}")

        except httpx.TimeoutException:
            result['status'] = 'timeout'
            result['error'] = 'Request timeout'
        except httpx.ConnectError:
            result['status'] = 'connection_error'
            result['error'] = 'Could not connect'
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)

        self._last_health_status[app_id] = result
        return result

    async def check_process_resources(self, app_id: str) -> Dict:
        """Check CPU and memory usage of a process."""
        result = {
            'app_id': app_id,
            'running': False,
            'cpu_percent': 0.0,
            'memory_mb': 0.0,
            'pid': None
        }

        status = self.process_manager.get_process_status(app_id)

        if status.get('running'):
            result['running'] = True
            result['cpu_percent'] = status.get('cpu_percent', 0.0)
            result['memory_mb'] = status.get('memory_mb', 0.0)
            result['pid'] = status.get('pid')

        return result

    def get_last_health_status(self, app_id: str) -> Optional[Dict]:
        """Get the last health check result for an app."""
        return self._last_health_status.get(app_id)

    async def perform_full_check(self, app_config: Dict) -> Dict:
        """Perform a full monitoring check for an app."""
        app_id = app_config.get('id')
        monitor_config = app_config.get('monitor', {})

        results = {
            'app_id': app_id,
            'timestamp': datetime.now().isoformat(),
            'process': None,
            'port': None,
            'health': None
        }

        if monitor_config.get('process'):
            results['process'] = await self.check_process_resources(app_id)

        if monitor_config.get('port') and app_config.get('port'):
            port_result = await self.check_port(app_id, app_config['port'])
            results['port'] = port_result

            self.database.record_health_check(
                app_id=app_id,
                port=app_config['port'],
                status='open' if port_result['open'] else 'closed',
                response_ms=port_result.get('response_time_ms'),
                error_message=port_result.get('error')
            )

        if monitor_config.get('http') and app_config.get('health_url'):
            health_result = await self.check_http_health(app_id, app_config['health_url'])
            results['health'] = health_result

            self.database.record_health_check(
                app_id=app_id,
                port=app_config.get('port'),
                status=health_result['status'],
                response_ms=health_result.get('response_ms'),
                error_message=health_result.get('error')
            )

        if monitor_config.get('cpu_ram') and results.get('process', {}).get('running'):
            self.database.record_process_metric(
                app_id=app_id,
                cpu_percent=results['process']['cpu_percent'],
                memory_mb=results['process']['memory_mb'],
                process_id=results['process'].get('pid')
            )

        return results

    async def monitor_app_loop(self, app_config: Dict, interval: int = 10):
        """Continuous monitoring loop for an app."""
        app_id = app_config.get('id')
        logger.info(f"Started monitoring loop for {app_id} (interval: {interval}s)")

        while self._running:
            try:
                await self.perform_full_check(app_config)
            except Exception as e:
                logger.error(f"Error in monitoring loop for {app_id}: {e}")

            await asyncio.sleep(interval)

        logger.info(f"Stopped monitoring loop for {app_id}")

    def start_monitoring(self, app_config: Dict, interval: int = 10):
        """Start monitoring an app."""
        if not self._running:
            self._running = True

        app_id = app_config.get('id')
        if app_id in self._monitoring_tasks:
            logger.warning(f"Already monitoring {app_id}")
            return

        task = asyncio.create_task(self.monitor_app_loop(app_config, interval))
        self._monitoring_tasks[app_id] = task
        logger.info(f"Started monitoring {app_id}")

    def stop_monitoring(self, app_id: str):
        """Stop monitoring a specific app."""
        if app_id in self._monitoring_tasks:
            self._monitoring_tasks[app_id].cancel()
            del self._monitoring_tasks[app_id]
            logger.info(f"Stopped monitoring {app_id}")

    def stop_all_monitoring(self):
        """Stop all monitoring tasks."""
        self._running = False
        for app_id in list(self._monitoring_tasks.keys()):
            self.stop_monitoring(app_id)
        logger.info("All monitoring stopped")

    def get_monitored_apps(self) -> list:
        """Get list of apps being monitored."""
        return list(self._monitoring_tasks.keys())