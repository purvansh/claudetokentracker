from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from claude_tray.parser import (
    discover_session_files,
    iter_jsonl_events,
    parse_event_dict,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_event_dict_minimal_assistant():
    d = {
        "type": "assistant",
        "timestamp": "2026-04-01T10:00:01.000Z",
        "requestId": "req_x",
        "message": {
            "id": "msg_x",
            "model": "claude-opus-4-6",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "cache_read_input_tokens": 2,
                "cache_creation": {"ephemeral_5m_input_tokens": 1, "ephemeral_1h_input_tokens": 0},
                "service_tier": "standard",
            },
        },
    }
    ev = parse_event_dict(d, "f")
    assert ev is not None
    assert ev.request_id == "req_x"
    assert ev.model == "claude-opus-4-6"
    assert ev.input_tokens == 10
    assert ev.output_tokens == 5
    assert ev.cache_read == 2
    assert ev.cache_creation_5m == 1
    assert ev.total_tokens == 18
    assert ev.timestamp.tzinfo == timezone.utc


def test_parse_event_dict_skips_non_assistant():
    assert parse_event_dict({"type": "user", "message": {}}, "f") is None
    assert parse_event_dict({"type": "permission-mode"}, "f") is None
    assert parse_event_dict({}, "f") is None


def test_parse_event_dict_skips_missing_usage():
    d = {
        "type": "assistant",
        "timestamp": "2026-04-01T10:00:01.000Z",
        "requestId": "req_y",
        "message": {"id": "m", "model": "x", "role": "assistant"},
    }
    assert parse_event_dict(d, "f") is None


def test_parse_event_dict_falls_back_to_message_id_when_no_request_id():
    d = {
        "type": "assistant",
        "timestamp": "2026-04-01T10:00:01.000Z",
        "message": {
            "id": "msg_only",
            "model": "claude-haiku-4-5",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }
    ev = parse_event_dict(d, "f")
    assert ev is not None and ev.request_id == "msg_only"


def test_iter_jsonl_events_reads_real_fixture():
    events = list(iter_jsonl_events(FIXTURES / "single_block.jsonl"))
    assert len(events) == 3
    assert {e.request_id for e in events} == {"req_001", "req_002", "req_003"}


def test_iter_jsonl_events_tolerates_malformed_last_line():
    events = list(iter_jsonl_events(FIXTURES / "multi_session" / "proj_a" / "session1.jsonl"))
    # 2 valid assistant events; the malformed final line is skipped without raising
    assert len(events) == 2


def test_discover_session_files_finds_nested_jsonl():
    files = discover_session_files(FIXTURES / "multi_session")
    assert len(files) == 2
    assert {p.name for p in files} == {"session1.jsonl"}


def test_discover_session_files_returns_empty_for_missing_dir():
    assert discover_session_files(FIXTURES / "does-not-exist") == []
