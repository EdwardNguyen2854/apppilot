import json
import pytest
import subprocess
from unittest.mock import patch

from .conftest import make_fake_completed


class TestCliRun:
    def test_run_with_default_args_returns_stdout_stderr_exit_code_and_duration(
        self, client, mock_subprocess_run
    ):
        mock_subprocess_run.return_value = make_fake_completed(
            returncode=0,
            stdout="hello world\n",
            stderr="",
        )

        resp = client.post("/api/apps/test-cli-tool/run", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["exit_code"] == 0
        assert data["stdout"] == "hello world\n"
        assert data["stderr"] == ""
        assert data["success"] is True
        assert data["timed_out"] is False
        assert isinstance(data["duration_sec"], (int, float))
        assert data["duration_sec"] >= 0
        assert data["args"] == ["--default"]

        invoked = mock_subprocess_run.call_args
        cmd = invoked.args[0]
        assert cmd[0].endswith("test-cli.exe")
        assert cmd[1:] == ["--default"]

    def test_run_with_overridden_args_replaces_defaults(
        self, client, mock_subprocess_run
    ):
        mock_subprocess_run.return_value = make_fake_completed(
            returncode=0, stdout="ok", stderr=""
        )

        resp = client.post(
            "/api/apps/test-cli-tool/run",
            json={"args": ["--flag", "value"]},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["args"] == ["--flag", "value"]
        cmd = mock_subprocess_run.call_args.args[0]
        assert cmd[1:] == ["--flag", "value"]

    def test_run_records_cli_run_row_in_database(
        self, client, mock_subprocess_run
    ):
        mock_subprocess_run.return_value = make_fake_completed(
            returncode=0, stdout="hello\n", stderr=""
        )

        resp = client.post("/api/apps/test-cli-tool/run", json={"args": ["--x"]})
        assert resp.status_code == 200

        history = client.get("/api/apps/test-cli-tool/run-history").json()["runs"]
        assert len(history) == 1
        run = history[0]
        assert run["app_id"] == "test-cli-tool"
        assert run["args"] == ["--x"]
        assert run["exit_code"] == 0
        assert run["success"] is True
        assert run["stdout_size"] == len("hello\n")
        assert run["stderr_size"] == 0
        assert isinstance(run["duration_sec"], (int, float))
        assert "started_at" in run and run["started_at"]

    def test_run_records_usage_event(self, client, mock_subprocess_run):
        mock_subprocess_run.return_value = make_fake_completed(
            returncode=0, stdout="ok", stderr=""
        )

        resp = client.post("/api/apps/test-cli-tool/run", json={"args": ["--y"]})
        assert resp.status_code == 200

        events = client.get(
            "/api/usage/events?app_id=test-cli-tool&limit=10"
        ).json()["events"]
        event = next(e for e in events if e["event_name"] == "cli_tool_run")
        details = json.loads(event["details_json"])
        assert details["args"] == ["--y"]
        assert details["success"] is True
        assert details["exit_code"] == 0

    def test_run_returns_run_id_and_history_uses_newest_first(
        self, client, mock_subprocess_run
    ):
        mock_subprocess_run.side_effect = [
            make_fake_completed(returncode=0, stdout="first", stderr=""),
            make_fake_completed(returncode=1, stdout="second", stderr="err"),
        ]

        first = client.post("/api/apps/test-cli-tool/run", json={"args": ["a"]}).json()
        second = client.post("/api/apps/test-cli-tool/run", json={"args": ["b"]}).json()

        assert first["exit_code"] == 0
        assert second["exit_code"] == 1

        history = client.get(
            "/api/apps/test-cli-tool/run-history?limit=10"
        ).json()["runs"]
        assert [r["args"] for r in history] == [["b"], ["a"]]
        assert [r["exit_code"] for r in history] == [1, 0]

    def test_run_on_nonexistent_app_returns_404(self, client):
        resp = client.post("/api/apps/does-not-exist/run", json={})
        assert resp.status_code == 404

    def test_run_on_non_cli_app_returns_400(self, client):
        resp = client.post("/api/apps/regular-web-app/run", json={})
        assert resp.status_code == 400
        assert "not a cli app" in resp.json()["detail"].lower()

    def test_run_with_non_string_arg_returns_422(self, client):
        resp = client.post(
            "/api/apps/test-cli-tool/run",
            json={"args": ["--ok", 42]},
        )
        assert resp.status_code == 422

    def test_run_history_on_nonexistent_app_returns_404(self, client):
        resp = client.get("/api/apps/does-not-exist/run-history")
        assert resp.status_code == 404

    def test_run_history_on_non_cli_app_returns_400(self, client):
        resp = client.get("/api/apps/regular-web-app/run-history")
        assert resp.status_code == 400
        assert "not a cli app" in resp.json()["detail"].lower()


class TestCliRunTimeout:
    def test_run_kills_process_on_timeout(self, client, mock_subprocess_run):
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(
            cmd=["x"], timeout=5
        )

        resp = client.post("/api/apps/test-cli-tool/run", json={"args": ["slow"]})

        assert resp.status_code == 200
        data = resp.json()
        assert data["timed_out"] is True
        assert data["success"] is False
        assert data["exit_code"] != 0
        assert "timeout" in (data.get("error_message") or "").lower()

        history = client.get("/api/apps/test-cli-tool/run-history").json()["runs"]
        assert len(history) == 1
        assert history[0]["success"] is False
        assert "timeout" in (history[0]["error_message"] or "").lower()


class TestCliRunMissingExecutable:
    def test_missing_exe_records_failure(self, client, test_config):
        test_config.get_app_by_id.side_effect = lambda app_id: next(
            (
                a for a in [
                    {
                        "id": "missing-cli",
                        "name": "Missing CLI",
                        "type": "cli",
                        "exe": "/definitely/does/not/exist/cli-tool",
                        "args": [],
                        "cwd": None,
                        "timeout": 30,
                    }
                ]
                if a["id"] == app_id
            ),
            None,
        )

        resp = client.post("/api/apps/missing-cli/run", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["exit_code"] != 0
        assert data["timed_out"] is False
        assert "no such file" in (data.get("error_message") or "").lower() or "not found" in (data.get("error_message") or "").lower()


class TestCliLifecycleNops:
    def test_start_on_cli_app_returns_nop(self, client):
        resp = client.post("/api/apps/test-cli-tool/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "run" in data["message"].lower()

    def test_stop_on_cli_app_returns_nop(self, client):
        resp = client.post("/api/apps/test-cli-tool/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "run-once" in data["message"].lower() or "run" in data["message"].lower()


class TestCliRunEdgeCases:
    def test_run_with_explicit_empty_args_uses_no_args(self, client, mock_subprocess_run):
        mock_subprocess_run.return_value = make_fake_completed(
            returncode=0, stdout="ok", stderr=""
        )

        resp = client.post(
            "/api/apps/test-cli-tool/run",
            json={"args": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["args"] == []
        cmd = mock_subprocess_run.call_args.args[0]
        assert cmd[1:] == []

    def test_run_does_not_re_register_app_on_every_invocation(self, client, mock_subprocess_run, test_db):
        mock_subprocess_run.return_value = make_fake_completed(
            returncode=0, stdout="ok", stderr=""
        )

        with patch.object(test_db, "register_app", wraps=test_db.register_app) as spy:
            client.post("/api/apps/test-cli-tool/run", json={})
            client.post("/api/apps/test-cli-tool/run", json={})
            assert spy.call_count == 0


class TestCliListApps:
    def test_list_apps_includes_last_run_for_cli(self, client, mock_subprocess_run):
        mock_subprocess_run.return_value = make_fake_completed(
            returncode=0, stdout="ok", stderr=""
        )
        client.post("/api/apps/test-cli-tool/run", json={"args": ["--x"]})

        resp = client.get("/api/apps")
        assert resp.status_code == 200
        cli = next(a for a in resp.json()["apps"] if a["id"] == "test-cli-tool")
        assert cli["type"] == "cli"
        assert cli["last_exit_code"] == 0
        assert cli["last_success"] is True
        assert cli["last_args"] == ["--x"]
        assert "last_run_at" in cli and cli["last_run_at"]

    def test_list_apps_omits_last_run_when_no_runs(self, client):
        resp = client.get("/api/apps")
        cli = next(a for a in resp.json()["apps"] if a["id"] == "test-cli-tool")
        assert cli["type"] == "cli"
        assert "last_run_at" not in cli
        assert "last_exit_code" not in cli


class TestCliStatus:
    def test_cli_status_reports_last_run_info(self, client, mock_subprocess_run):
        mock_subprocess_run.return_value = make_fake_completed(
            returncode=0, stdout="hello", stderr=""
        )
        client.post("/api/apps/test-cli-tool/run", json={"args": ["--x"]})

        resp = client.get("/api/apps/test-cli-tool/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "cli"
        assert data["last_exit_code"] == 0
        assert data["last_success"] is True
        assert data["last_args"] == ["--x"]
        assert "last_run_at" in data and data["last_run_at"]

    def test_cli_status_without_runs_returns_nulls(self, client):
        resp = client.get("/api/apps/test-cli-tool/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "cli"
        assert data.get("last_exit_code") is None
        assert data.get("last_success") is None
        assert data.get("last_args") is None
        assert data.get("last_run_at") is None
