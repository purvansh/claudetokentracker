from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude_tray.parser import iter_jsonl_events
from claude_tray.session import (
    build_blocks,
    compute_state,
    dedupe_events,
    format_countdown,
    format_tokens_short,
)

FIXTURES = Path(__file__).parent / "fixtures"
UTC = timezone.utc


def _events(path: str):
    return list(iter_jsonl_events(FIXTURES / path))


def test_single_block_groups_three_events():
    evs = _events("single_block.jsonl")
    blocks = build_blocks(evs, session_hours=5, now=datetime(2026, 4, 1, 14, 0, tzinfo=UTC))
    assert len(blocks) == 1
    assert blocks[0].start == datetime(2026, 4, 1, 10, 0, 1, tzinfo=UTC)
    assert blocks[0].total_tokens == sum(e.total_tokens for e in evs)


def test_two_blocks_separated_by_gap():
    evs = _events("two_blocks_gap.jsonl")
    blocks = build_blocks(evs, session_hours=5, now=datetime(2026, 4, 1, 16, 0, tzinfo=UTC))
    assert len(blocks) == 2
    assert blocks[0].start == datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
    assert blocks[1].start == datetime(2026, 4, 1, 15, 0, tzinfo=UTC)


def test_overflow_forces_new_block():
    evs = _events("overflow_5h.jsonl")
    blocks = build_blocks(evs, session_hours=5, now=datetime(2026, 4, 1, 15, 0, tzinfo=UTC))
    # 09:00, 11:00, 13:30 fit in block 1; 14:30 is +5h30 from start → forces a split.
    assert len(blocks) == 2
    assert len(blocks[0].events) == 3
    assert len(blocks[1].events) == 2


def test_future_event_is_dropped():
    evs = _events("future_timestamp.jsonl")
    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    state = compute_state(evs, now=now, session_hours=5)
    # only the 09:00 event survives
    assert state.active is not None
    assert len(state.active.events) == 1
    assert state.active.events[0].request_id == "req_030"


def test_compute_state_is_idle_when_active_block_expired():
    evs = _events("single_block.jsonl")
    # last event at 13:00 + 5h = 18:00; at 19:00 the block has expired
    now = datetime(2026, 4, 1, 19, 0, tzinfo=UTC)
    state = compute_state(evs, now=now, session_hours=5)
    assert state.is_idle is True
    assert state.active is None
    assert state.next_reset is None


def test_compute_state_picks_active_block():
    evs = _events("two_blocks_gap.jsonl")
    now = datetime(2026, 4, 1, 16, 0, tzinfo=UTC)
    state = compute_state(evs, now=now, session_hours=5)
    assert state.active is not None
    assert state.active.start == datetime(2026, 4, 1, 15, 0, tzinfo=UTC)
    assert state.next_reset == datetime(2026, 4, 1, 20, 0, tzinfo=UTC)


def test_dedupe_keeps_first_occurrence():
    evs = list(iter_jsonl_events(FIXTURES / "multi_session" / "proj_a" / "session1.jsonl")) + list(
        iter_jsonl_events(FIXTURES / "multi_session" / "proj_b" / "session1.jsonl")
    )
    deduped = dedupe_events(evs)
    ids = [e.request_id for e in deduped]
    assert ids.count("req_DUP") == 1


def test_format_countdown():
    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    assert format_countdown(now + timedelta(minutes=42), now) == "42m"
    assert format_countdown(now + timedelta(hours=3, minutes=11), now) == "3h11m"
    assert format_countdown(now - timedelta(seconds=1), now) == "0m"


def test_format_tokens_short():
    assert format_tokens_short(0) == "0"
    assert format_tokens_short(950) == "950"
    assert format_tokens_short(1500) == "1.5k"
    assert format_tokens_short(15000) == "15k"
    assert format_tokens_short(1_500_000) == "1.50M"
