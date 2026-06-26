import json
import pytest
from unittest.mock import AsyncMock

from .conftest import (
    create_mock_process,
    VALID_INITIALIZE_RESPONSE,
    VALID_TOOLS_RESPONSE,
    VALID_RESOURCES_RESPONSE,
    VALID_PROMPTS_RESPONSE,
    VALID_TOOL_CALL_RESPONSE,
    ERROR_TOOL_CALL_RESPONSE,
    IS_ERROR_TOOL_CALL_RESPONSE,
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


class TestMCPToolInvocation:
    def test_valid_known_tool_call_returns_content_and_duration(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
            VALID_RESOURCES_RESPONSE,
            VALID_PROMPTS_RESPONSE,
            VALID_TOOL_CALL_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")

        resp = client.post("/api/apps/test-mcp-server/mcp/call", json={
            "tool": "get_weather",
            "arguments": {"location": "Hanoi"},
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == [{"type": "text", "text": "Weather in Hanoi: 30 C"}]
        assert data["isError"] is False
        assert isinstance(data["duration_ms"], int)
        assert data["duration_ms"] >= 0

    def test_missing_required_argument_rejected_before_calling_server(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
            VALID_RESOURCES_RESPONSE,
            VALID_PROMPTS_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")

        resp = client.post("/api/apps/test-mcp-server/mcp/call", json={
            "tool": "get_weather",
            "arguments": {},
        })

        assert resp.status_code == 422
        assert "location" in resp.json()["detail"].lower()

    def test_blank_required_argument_is_rejected(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
            VALID_RESOURCES_RESPONSE,
            VALID_PROMPTS_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")

        resp = client.post("/api/apps/test-mcp-server/mcp/call", json={
            "tool": "get_weather",
            "arguments": {"location": ""},
        })

        assert resp.status_code == 422
        assert "location" in resp.json()["detail"].lower()

    def test_unknown_tool_returns_graceful_error(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
            VALID_RESOURCES_RESPONSE,
            VALID_PROMPTS_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")

        resp = client.post("/api/apps/test-mcp-server/mcp/call", json={
            "tool": "does_not_exist",
            "arguments": {},
        })

        assert resp.status_code == 404
        assert "unknown mcp tool" in resp.json()["detail"].lower()

    def test_disconnected_server_returns_graceful_error(self, client):
        resp = client.post("/api/apps/test-mcp-server/mcp/call", json={
            "tool": "echo",
            "arguments": {"message": "hi"},
        })

        assert resp.status_code == 400
        assert "not running" in resp.json()["detail"].lower()

    def test_history_returns_invocations_newest_first(self, client, mock_asyncio_subprocess):
        second_call_response = {
            "jsonrpc": "2.0",
            "id": 6,
            "result": {
                "content": [{"type": "text", "text": "Echo: hi"}],
                "isError": False,
            },
        }
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
            VALID_RESOURCES_RESPONSE,
            VALID_PROMPTS_RESPONSE,
            VALID_TOOL_CALL_RESPONSE,
            second_call_response,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")
        client.post("/api/apps/test-mcp-server/mcp/call", json={
            "tool": "get_weather",
            "arguments": {"location": "Hanoi"},
        })
        client.post("/api/apps/test-mcp-server/mcp/call", json={
            "tool": "echo",
            "arguments": {"message": "hi"},
        })

        resp = client.get("/api/apps/test-mcp-server/mcp/history")

        assert resp.status_code == 200
        invocations = resp.json()["invocations"]
        assert [row["tool_name"] for row in invocations] == ["echo", "get_weather"]
        assert invocations[0]["success"] is True
        assert invocations[0]["arguments"] == {"message": "hi"}
        assert invocations[0]["result_summary"] == "Echo: hi"

    def test_failed_call_creates_history_row(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
            VALID_RESOURCES_RESPONSE,
            VALID_PROMPTS_RESPONSE,
            ERROR_TOOL_CALL_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")
        resp = client.post("/api/apps/test-mcp-server/mcp/call", json={
            "tool": "get_weather",
            "arguments": {"location": "Hanoi"},
        })

        assert resp.status_code == 502
        history = client.get("/api/apps/test-mcp-server/mcp/history").json()["invocations"]
        assert len(history) == 1
        assert history[0]["success"] is False
        assert "invalid tool arguments" in history[0]["error_message"].lower()

    def test_is_error_result_preserves_error_content_in_history(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
            VALID_RESOURCES_RESPONSE,
            VALID_PROMPTS_RESPONSE,
            IS_ERROR_TOOL_CALL_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")
        resp = client.post("/api/apps/test-mcp-server/mcp/call", json={
            "tool": "get_weather",
            "arguments": {"location": "Hanoi"},
        })

        assert resp.status_code == 200
        assert resp.json()["isError"] is True
        history = client.get("/api/apps/test-mcp-server/mcp/history").json()["invocations"]
        assert history[0]["success"] is False
        assert history[0]["error_message"] == "Error: Tool-level failure"
        assert history[0]["result_summary"] == "Error: Tool-level failure"

    def test_status_includes_recent_invocation_count(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
            VALID_RESOURCES_RESPONSE,
            VALID_PROMPTS_RESPONSE,
            VALID_TOOL_CALL_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")
        client.post("/api/apps/test-mcp-server/mcp/call", json={
            "tool": "get_weather",
            "arguments": {"location": "Hanoi"},
        })

        mcp_status = client.get("/api/apps/test-mcp-server/mcp/status").json()
        app_status = client.get("/api/apps/test-mcp-server/status").json()
        assert mcp_status["recent_invocation_count"] == 1
        assert app_status["recent_invocation_count"] == 1

    def test_usage_event_recorded_for_tool_call(self, client, mock_asyncio_subprocess):
        mock_proc = create_mock_process([
            VALID_INITIALIZE_RESPONSE,
            VALID_TOOLS_RESPONSE,
            VALID_RESOURCES_RESPONSE,
            VALID_PROMPTS_RESPONSE,
            VALID_TOOL_CALL_RESPONSE,
        ])
        mock_asyncio_subprocess.return_value = mock_proc

        client.post("/api/apps/test-mcp-server/start")
        client.post("/api/apps/test-mcp-server/mcp/call", json={
            "tool": "get_weather",
            "arguments": {"location": "Hanoi"},
        })

        events = client.get("/api/usage/events?app_id=test-mcp-server&limit=5").json()["events"]
        event = next(e for e in events if e["event_name"] == "mcp_tool_called")
        details = json.loads(event["details_json"])
        assert event["success"] == 1
        assert details["tool_name"] == "get_weather"
        assert details["success"] is True
        assert isinstance(details["duration_ms"], int)


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
