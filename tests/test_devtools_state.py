"""Tests for the dev-only deployment controls in AppState."""
from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

pytest.importorskip("reflex")

from reflex_app.aequitas_rx.state import (  # noqa: E402
    AppState,
    _import_broadcast_command,
    _local_deploy_command,
    _sepolia_deploy_command,
)


def test_local_deploy_command_requires_anvil_pk():
    raised = False
    try:
        _local_deploy_command({})
    except ValueError:
        raised = True
    assert raised


def test_local_deploy_command_shape():
    cmd = _local_deploy_command({"ANVIL_PK": "0xabc"})
    assert cmd[:4] == ["forge", "script", "script/Deploy.s.sol", "--rpc-url"]
    assert "http://127.0.0.1:8545" in cmd
    assert "--private-key" in cmd
    assert "0xabc" in cmd
    assert "--broadcast" in cmd


def test_import_broadcast_command_uses_repo_python_and_chain():
    cmd = _import_broadcast_command(
        broadcast_path="/tmp/run-latest.json",  # type: ignore[arg-type]
        registry_path="/tmp/local.json",  # type: ignore[arg-type]
        chain_id=31337,
    )
    assert cmd[0] == os.sys.executable
    assert "import_broadcast.py" in cmd[1]
    assert cmd[-2:] == ["--chain-id", "31337"]


def test_sepolia_deploy_command_uses_env_rpc_or_alias():
    cmd = _sepolia_deploy_command({"DEPLOYER_PK": "0xdef", "SEPOLIA_RPC_URL": "https://rpc.example"})
    assert cmd[:4] == ["forge", "script", "script/Deploy.s.sol", "--rpc-url"]
    assert "https://rpc.example" in cmd
    assert "--verify" in cmd


def test_deploy_local_stack_success_updates_status_and_refreshes():
    state = AppState()
    with patch.dict(os.environ, {"ANVIL_PK": "0xabc"}, clear=False):
        with patch("reflex_app.aequitas_rx.state._run_subprocess") as run:
            run.return_value = subprocess.CompletedProcess(
                args=["forge"],
                returncode=0,
                stdout="deploy ok",
                stderr="",
            )
            with patch.object(AppState, "_refresh", autospec=True) as refresh:
                state.deploy_local_stack()
    assert state.devtools_status == "success"
    assert state.devtools_target == "local"
    assert "Local stack deployed" in state.devtools_message
    assert "deploy ok" in state.devtools_logs
    assert "[REDACTED]" in state.devtools_last_command
    refresh.assert_called_once_with(state)


def test_deploy_local_stack_failure_captures_logs():
    state = AppState()
    with patch.dict(os.environ, {"ANVIL_PK": "0xabc"}, clear=False):
        with patch("reflex_app.aequitas_rx.state._run_subprocess") as run:
            run.return_value = subprocess.CompletedProcess(
                args=["forge"],
                returncode=1,
                stdout="",
                stderr="forge failed",
            )
            with patch.object(AppState, "_refresh", autospec=True) as refresh:
                state.deploy_local_stack()
    assert state.devtools_status == "failed"
    assert "exit code 1" in state.devtools_message
    assert "forge failed" in state.devtools_logs
    refresh.assert_called_once_with(state)


def test_reload_deployment_registry_reports_source():
    state = AppState()
    state.registry_source_path = "contracts/deployments/local.json"
    with patch.object(AppState, "_refresh", autospec=True) as refresh:
        state.reload_deployment_registry()
    assert state.devtools_status == "success"
    assert "contracts/deployments/local.json" in state.devtools_message
    refresh.assert_called_once_with(state)
