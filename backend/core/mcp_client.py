import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class MCPClient:
    """Manages JSON-RPC lifecycle for an MCP server over stdio transport."""

    def __init__(self):
        self._status = "disconnected"
        self._error_message: Optional[str] = None
        self._initialized_at: Optional[str] = None
        self._tools: List[Dict] = []
        self._resources: List[Dict] = []
        self._prompts: List[Dict] = []
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._stderr_task: Optional[asyncio.Task] = None

    @property
    def status(self) -> str:
        return self._status

    @property
    def error_message(self) -> Optional[str]:
        return self._error_message

    @property
    def initialized_at(self) -> Optional[str]:
        return self._initialized_at

    @property
    def tools(self) -> List[Dict]:
        return self._tools

    @property
    def resources(self) -> List[Dict]:
        return self._resources

    @property
    def prompts(self) -> List[Dict]:
        return self._prompts

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def connect(
        self,
        transport: str = "stdio",
        exe: Optional[str] = None,
        args: Optional[List[str]] = None,
        cwd: Optional[str] = None,
        url: Optional[str] = None,
    ) -> None:
        self._status = "connecting"
        self._error_message = None

        try:
            if transport == "stdio":
                await self._connect_stdio(exe, args, cwd)
            else:
                await self._connect_sse(url)
        except Exception as e:
            self._status = "error"
            self._error_message = str(e)
            logger.error(f"MCP connect failed: {e}")
            raise

    async def _connect_stdio(
        self, exe: Optional[str], args: Optional[List[str]], cwd: Optional[str]
    ) -> None:
        if not exe:
            raise ValueError("exe is required for stdio transport")

        self._process = await asyncio.create_subprocess_exec(
            exe,
            *(args or []),
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._stderr_task = asyncio.create_task(self._read_stderr_loop())

    async def _connect_sse(self, url: Optional[str]) -> None:
        if not url:
            raise ValueError("url is required for SSE transport")
        raise NotImplementedError("SSE transport not yet implemented")

    async def _read_stderr_loop(self) -> None:
        try:
            async for line_bytes in self._process.stderr:
                line = line_bytes.decode().strip()
                if line:
                    logger.debug(f"MCP stderr: {line}")
        except Exception:
            pass

    async def _read_line(self) -> Optional[str]:
        line_bytes = await asyncio.wait_for(
            self._process.stdout.readline(),
            timeout=30.0,
        )
        if not line_bytes:
            return None
        return line_bytes.decode().strip()

    async def _send_request(self, method: str, params: Optional[Dict] = None) -> Dict:
        req_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        payload = json.dumps(request) + "\n"
        self._process.stdin.write(payload.encode())
        await self._process.stdin.drain()

        while True:
            line = await self._read_line()
            if line is None:
                raise ConnectionError("MCP server closed connection")
            if not line:
                continue

            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(f"MCP: non-JSON output: {line[:200]}")
                continue

            if response.get("id") == req_id:
                if "error" in response:
                    error = response["error"]
                    raise RuntimeError(f"MCP error: {error.get('message', 'unknown')}")
                return response.get("result", {})

    async def initialize(self) -> Dict:
        try:
            result = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "apppilot", "version": "1.0.0"},
            })
            self._capabilities = result.get("capabilities", {})
            self._status = "initialized"
            self._initialized_at = datetime.now().isoformat()

            try:
                notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
                self._process.stdin.write(json.dumps(notification).encode() + b"\n")
                await self._process.stdin.drain()
            except Exception:
                pass

            return result
        except Exception as e:
            self._status = "error"
            self._error_message = str(e)
            raise

    async def list_tools(self) -> List[Dict]:
        result = await self._send_request("tools/list")
        self._tools = result.get("tools", [])
        return self._tools

    async def list_resources(self) -> List[Dict]:
        result = await self._send_request("resources/list")
        self._resources = result.get("resources", [])
        return self._resources

    async def list_prompts(self) -> List[Dict]:
        result = await self._send_request("prompts/list")
        self._prompts = result.get("prompts", [])
        return self._prompts

    async def disconnect(self) -> None:
        try:
            if self._status == "initialized":
                try:
                    shutdown = {
                        "jsonrpc": "2.0",
                        "method": "shutdown",
                        "params": {},
                    }
                    self._process.stdin.write(json.dumps(shutdown).encode() + b"\n")
                    await self._process.stdin.drain()
                except Exception:
                    pass
        finally:
            if self._stderr_task:
                self._stderr_task.cancel()
                self._stderr_task = None
            if self._process:
                try:
                    self._process.terminate()
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except Exception:
                    try:
                        self._process.kill()
                        await self._process.wait()
                    except Exception:
                        pass
                self._process = None
            self._status = "disconnected"
            self._tools = []
            self._resources = []
            self._prompts = []
            self._capabilities = None
            self._initialized_at = None
            self._error_message = None


class MCPManager:
    """Manages MCPClient instances per app."""

    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}

    async def connect(self, app_id: str, app_config: Dict) -> MCPClient:
        if app_id in self._clients:
            await self.disconnect(app_id)
        client = MCPClient()
        transport = app_config.get("transport", "stdio")

        await client.connect(
            transport=transport,
            exe=app_config.get("exe"),
            args=app_config.get("args", []),
            cwd=app_config.get("cwd"),
            url=app_config.get("url"),
        )

        try:
            await client.initialize()
        except Exception as e:
            self._clients[app_id] = client
            raise

        try:
            await client.list_tools()
        except Exception as e:
            logger.warning(f"MCP {app_id}: tools/list failed: {e}")

        try:
            await client.list_resources()
        except Exception as e:
            logger.warning(f"MCP {app_id}: resources/list failed: {e}")

        try:
            await client.list_prompts()
        except Exception as e:
            logger.warning(f"MCP {app_id}: prompts/list failed: {e}")

        self._clients[app_id] = client
        return client

    async def disconnect(self, app_id: str) -> None:
        client = self._clients.pop(app_id, None)
        if client:
            await client.disconnect()

    async def disconnect_all(self) -> None:
        for app_id in list(self._clients.keys()):
            await self.disconnect(app_id)

    def get_client(self, app_id: str) -> Optional[MCPClient]:
        return self._clients.get(app_id)

    def get_status(self, app_id: str) -> Dict:
        client = self._clients.get(app_id)
        if not client:
            return {
                "status": "disconnected",
                "tool_count": 0,
                "resource_count": 0,
                "prompt_count": 0,
                "initialized_at": None,
                "error_message": None,
            }
        return {
            "status": client.status,
            "tool_count": len(client.tools),
            "resource_count": len(client.resources),
            "prompt_count": len(client.prompts),
            "initialized_at": client.initialized_at,
            "error_message": client.error_message,
        }
