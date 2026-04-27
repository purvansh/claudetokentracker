"""End-to-end smoke test: --once --json against fixtures."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = ROOT / "tests" / "fixtures" / "multi_session"


def test_once_json_emits_valid_payload(tmp_path: Path):
    env = os.environ.copy()
    # isolate config + cache so the test never touches the real user dirs
    env["XDG_CONFIG_HOME"] = str(tmp_path / "cfg")
    env["XDG_CACHE_HOME"] = str(tmp_path / "cache")
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    out = subprocess.check_output(
        [sys.executable, "-m", "claude_tray", "--once", "--json", "--data-dir", str(FIXTURES)],
        env=env, text=True, timeout=30,
    )
    payload = json.loads(out)
    assert "now" in payload
    assert "is_idle" in payload
    assert "today_total" in payload
    assert "week_total" in payload
    assert "pricing_version" in payload
    # active should either be null or have these keys
    if payload["active"] is not None:
        for k in ("start", "end", "tokens", "cost", "by_model"):
            assert k in payload["active"]


def test_status_command_runs(tmp_path: Path):
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "cfg")
    env["XDG_CACHE_HOME"] = str(tmp_path / "cache")
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    out = subprocess.check_output(
        [sys.executable, "-m", "claude_tray", "status", "--data-dir", str(FIXTURES)],
        env=env, text=True, timeout=30,
    )
    assert "Claude Code session status" in out


def test_bar_json_command_runs(tmp_path: Path):
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "cfg")
    env["XDG_CACHE_HOME"] = str(tmp_path / "cache")
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    out = subprocess.check_output(
        [sys.executable, "-m", "claude_tray", "bar", "--format", "json", "--data-dir", str(FIXTURES)],
        env=env, text=True, timeout=30,
    )
    payload = json.loads(out)
    assert "text" in payload and "tooltip" in payload and "class" in payload
