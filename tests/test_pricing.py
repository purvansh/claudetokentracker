from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from claude_tray.parser import UsageEvent
from claude_tray.pricing import event_cost, events_cost, load_pricing


def _ev(model: str, **kwargs) -> UsageEvent:
    return UsageEvent(
        timestamp=datetime(2026, 4, 1, tzinfo=timezone.utc),
        request_id=kwargs.get("rid", "r"),
        message_id="m",
        model=model,
        input_tokens=kwargs.get("input_tokens", 0),
        output_tokens=kwargs.get("output_tokens", 0),
        cache_creation_5m=kwargs.get("cache_creation_5m", 0),
        cache_creation_1h=kwargs.get("cache_creation_1h", 0),
        cache_read=kwargs.get("cache_read", 0),
        service_tier="standard",
        source_file="x",
    )


def test_load_bundled_pricing_has_known_models():
    table = load_pricing(None)
    assert "claude-opus-4-6" in table.models
    assert "claude-sonnet-4-6" in table.models
    assert "claude-haiku-4-5" in table.models


def test_event_cost_opus_matches_rate_card():
    table = load_pricing(None)
    ev = _ev("claude-opus-4-6", input_tokens=1_000_000, output_tokens=1_000_000)
    cost = event_cost(ev, table)
    # 1M input @ $15 + 1M output @ $75 = $90
    assert abs(cost - 90.0) < 1e-9


def test_event_cost_unknown_model_is_zero(caplog):
    table = load_pricing(None)
    ev = _ev("claude-something-future", input_tokens=1_000_000)
    assert event_cost(ev, table) == 0.0
    # second call should not log a duplicate warning
    event_cost(ev, table)


def test_event_cost_uses_aliases():
    table = load_pricing(None)
    ev = _ev("claude-opus-4-6-20260101", input_tokens=1_000_000)
    # Aliased to claude-opus-4-6 ($15/Mtok)
    assert abs(event_cost(ev, table) - 15.0) < 1e-9


def test_events_cost_sums(tmp_path: Path):
    table = load_pricing(None)
    events = [
        _ev("claude-opus-4-6", input_tokens=1_000_000),
        _ev("claude-sonnet-4-6", output_tokens=1_000_000),
    ]
    # opus 1M input = $15 ; sonnet 1M output = $15 ; total $30
    assert abs(events_cost(events, table) - 30.0) < 1e-9


def test_pricing_override_takes_effect(tmp_path: Path):
    override = tmp_path / "model-pricing.json"
    override.write_text(
        json.dumps(
            {
                "version": 99,
                "updated": "2099-01-01",
                "models": {"claude-opus-4-6": {"input": 1.0, "output": 2.0, "cache_read": 0.0,
                                               "cache_write_5m": 0.0, "cache_write_1h": 0.0}},
                "model_aliases": {},
            }
        )
    )
    table = load_pricing(override)
    assert table.version == 99
    ev = _ev("claude-opus-4-6", input_tokens=1_000_000)
    assert abs(event_cost(ev, table) - 1.0) < 1e-9
