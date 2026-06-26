import pytest
import tempfile
import json
import os
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi.testclient import TestClient

from backend.core.config import Config
from backend.core.database import Database
from backend.app import create_app

SAMPLE_APPS = [
    {
        "id": "test-mcp-server",
        "name": "Test MCP Server",
        "type": "mcp",
        "transport": "stdio",
        "exe": "apps/mcp-server/server.exe",
        "args": ["--port", "9000"],
        "cwd": None,
        "url": None,
        "auto_start": False,
        "log_file": "logs/mcp-server.log",
        "monitor": {"process": True, "port": False, "http": False, "cpu_ram": True},
    },
    {
        "id": "regular-web-app",
        "name": "Regular Web",
        "type": "web",
        "exe": "apps/web/web.exe",
        "args": [],
        "port": 8787,
        "auto_start": False,
        "monitor": {"process": True, "port": True, "http": False, "cpu_ram": True},
    },
]

VALID_INITIALIZE_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        "serverInfo": {"name": "test-server", "version": "1.0.0"},
    },
}

VALID_TOOLS_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 2,
    "result": {
        "tools": [
            {
                "name": "get_weather",
                "description": "Get weather for a location",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                    },
                    "required": ["location"],
                },
            },
            {
                "name": "echo",
                "description": "Echo back the input",
                "inputSchema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            },
        ]
    },
}

VALID_RESOURCES_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 3,
    "result": {
        "resources": [
            {
                "uri": "file:///data/doc.txt",
                "name": "Document",
                "description": "A sample document",
                "mimeType": "text/plain",
            }
        ]
    },
}

VALID_PROMPTS_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 4,
    "result": {
        "prompts": [
            {
                "name": "greet",
                "description": "Generate a greeting",
                "arguments": [
                    {"name": "name", "description": "The name to greet", "required": True}
                ],
            }
        ]
    },
}

VALID_TOOL_CALL_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 5,
    "result": {
        "content": [
            {"type": "text", "text": "Weather in Hanoi: 30 C"}
        ],
        "isError": False,
    },
}

ERROR_TOOL_CALL_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 5,
    "error": {"code": -32602, "message": "Invalid tool arguments", "data": None},
}

IS_ERROR_TOOL_CALL_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 5,
    "result": {
        "content": [
            {"type": "text", "text": "Tool-level failure"}
        ],
        "isError": True,
    },
}

ERROR_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 1,
    "error": {"code": -32603, "message": "Sample handshake error", "data": None},
}


class AsyncBytesIterator:
    """Async iterator that yields bytes lines. Supports readline for mock subprocess stdout."""
    def __init__(self, lines):
        self.lines = lines
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.lines):
            raise StopAsyncIteration
        line = self.lines[self.index]
        self.index += 1
        return line

    async def readline(self):
        if self.index >= len(self.lines):
            return b""
        line = self.lines[self.index]
        self.index += 1
        return line


def create_mock_process(responses):
    """Create a mock subprocess that returns the given JSON-RPC responses on stdout."""
    encoded_lines = [json.dumps(r).encode() + b"\n" for r in responses]
    async_iter = AsyncBytesIterator(encoded_lines)

    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_process.returncode = None
    mock_process.stdout = async_iter

    mock_stdin = MagicMock()
    mock_stdin.write = MagicMock()
    mock_stdin.drain = AsyncMock(return_value=None)
    mock_process.stdin = mock_stdin

    mock_process.stderr = AsyncBytesIterator([])
    mock_process.wait = AsyncMock(return_value=0)
    mock_process.kill = MagicMock()
    mock_process.terminate = MagicMock()

    return mock_process


@pytest.fixture
def mock_asyncio_subprocess():
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def test_config():
    config = MagicMock(spec=Config)
    config.get_apps.return_value = SAMPLE_APPS
    config.get_app_by_id.side_effect = lambda app_id: next(
        (a for a in SAMPLE_APPS if a["id"] == app_id), None
    )
    config.get_machine_id.return_value = "TESTMACHINE123"
    config.get_user_alias.return_value = "test-user"
    config.get.return_value = None
    return config


@pytest.fixture
def test_db():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    db_path = tmp.name
    tmp.close()

    db = Database(db_path=db_path)
    db.initialize()

    yield db

    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def client(test_config, test_db, mock_asyncio_subprocess):
    app = create_app(config=test_config, database=test_db)
    return TestClient(app)
