import json
import pytest
from unittest.mock import AsyncMock

from .conftest import (
    create_mock_process,
    VALID_INITIALIZE_RESPONSE,
    VALID_TOOLS_RESPONSE,
    VALID_RESOURCES_RESPONSE,
    VALID_PROMPTS_RESPONSE,
    ERROR_RESPONSE,
)


class TestMCPStatus:
    def test_mcp_status_disconnected(self, client):
        resp = client.get("/api/apps/test-mcp-server/mcp/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "disconnected"
        assert data["tool_count"] == 0
        assert data["resource_count"] == 0
        assert data["prompt_count"] == 0

    def test_mcp_status_nonexistent_app(self, client):
        resp = client.get("/api/apps/nonexistent/mcp/status")
        assert resp.status_code == 404

    def test_mcp_status_non_mcp_app(self, client):
        resp = client.get("/api/apps/regular-web-app/mcp/status")
        assert resp.status_code == 400
        assert "not an mcp app" in resp.json()["detail"].lower()


class TestMCPDiscovery:
    def test_mcp_start_and_discover_tools(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        resp = client.post("/api/apps/test-mcp-server/start")
        assert resp.status_code == 200

        tools_resp = client.get("/api/apps/test-mcp-server/mcp/tools")
        assert tools_resp.status_code == 200
        data = tools_resp.json()
        assert "tools" in data
        assert len(data["tools"]) == 2
        assert data["tools"][0]["name"] == "get_weather"
        assert data["tools"][1]["name"] == "echo"

    def test_mcp_start_and_discover_resources(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
            VALID_RESOURCES_RESPONSE,
            VALID_PROMPTS_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")

        resp = client.get("/api/apps/test-mcp-server/mcp/resources")
        assert resp.status_code == 200
        data = resp.json()
        assert "resources" in data
        assert len(data["resources"]) == 1
        assert data["resources"][0]["name"] == "Document"

    def test_mcp_start_and_discover_prompts(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
            VALID_RESOURCES_RESPONSE,
            VALID_PROMPTS_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")

        resp = client.get("/api/apps/test-mcp-server/mcp/prompts")
        assert resp.status_code == 200
        data = resp.json()
        assert "prompts" in data
        assert len(data["prompts"]) == 1
        assert data["prompts"][0]["name"] == "greet"

    def test_mcp_status_after_start(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")

        resp = client.get("/api/apps/test-mcp-server/mcp/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "initialized"
        assert data["tool_count"] == 2
        assert data["initialized_at"] is not None

    def test_mcp_tools_empty_when_not_started(self, client):
        client.get("/api/apps/test-mcp-server/mcp/status")
        resp = client.get("/api/apps/test-mcp-server/mcp/tools")
        assert resp.status_code in (200, 400)
        if resp.status_code == 400:
            assert "not running" in resp.json()["detail"].lower()


class TestMCPError:
    def test_mcp_handshake_error(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([ERROR_RESPONSE])
        mock_asyncio_subprocess.return_value = mock_proc

        resp = client.post("/api/apps/test-mcp-server/start")
        assert resp.status_code == 200

        status_resp = client.get("/api/apps/test-mcp-server/mcp/status")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["status"] == "error"
        assert data["error_message"] is not None

    def test_mcp_stop_disconnects(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")

        status_resp = client.get("/api/apps/test-mcp-server/mcp/status")
        assert status_resp.json()["status"] == "initialized"

        client.post("/api/apps/test-mcp-server/stop")

        status_resp = client.get("/api/apps/test-mcp-server/mcp/status")
        assert status_resp.json()["status"] == "disconnected"


class TestAppStatusIntegration:
    def test_app_status_includes_mcp_info(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")

        resp = client.get("/api/apps/test-mcp-server/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mcp_status"] == "initialized"
        assert data["tool_count"] == 2
        assert data["type"] == "mcp"

    def test_list_apps_includes_mcp_type(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")

        resp = client.get("/api/apps")
        assert resp.status_code == 200
        data = resp.json()
        mcp_apps = [a for a in data["apps"] if a["type"] == "mcp"]
        assert len(mcp_apps) == 1
        assert mcp_apps[0]["mcp_status"] == "initialized"
        assert mcp_apps[0]["tool_count"] == 2
