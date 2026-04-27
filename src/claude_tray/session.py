"""5-hour rolling session ("block") computation, matching the ccusage algorithm."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .parser import UsageEvent

log = logging.getLogger(__name__)


@dataclass
class Block:
    start: datetime
    duration: timedelta
    events: list[UsageEvent] = field(default_factory=list)

    @property
    def end(self) -> datetime:
        return self.start + self.duration

    @property
    def total_tokens(self) -> int:
        return sum(e.total_tokens for e in self.events)

    @property
    def by_model(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.events:
            out[e.model] = out.get(e.model, 0) + e.total_tokens
        return out


@dataclass
class SessionState:
    now: datetime
    active: Block | None
    next_reset: datetime | None
    is_idle: bool
    today_total: int
    week_total: int
    by_model_active: dict[str, int]
    all_blocks: list[Block]


def dedupe_events(events: Iterable[UsageEvent]) -> list[UsageEvent]:
    seen: set[str] = set()
    out: list[UsageEvent] = []
    for ev in events:
        if ev.request_id in seen:
            continue
        seen.add(ev.request_id)
        out.append(ev)
    return out


def build_blocks(
    events: Iterable[UsageEvent],
    session_hours: int = 5,
    *,
    now: datetime | None = None,
    future_skew_seconds: int = 60,
) -> list[Block]:
    """Group sorted events into rolling N-hour blocks (ccusage rules)."""
    span = timedelta(hours=session_hours)
    cutoff_future = (now or datetime.now(tz=timezone.utc)) + timedelta(seconds=future_skew_seconds)
    sorted_events = sorted(
        (e for e in events if e.timestamp <= cutoff_future),
        key=lambda e: e.timestamp,
    )
    blocks: list[Block] = []
    for ev in sorted_events:
        if not blocks:
            blocks.append(Block(start=ev.timestamp, duration=span, events=[ev]))
            continue
        cur = blocks[-1]
        prev = cur.events[-1]
        gap = ev.timestamp - prev.timestamp
        offset = ev.timestamp - cur.start
        if gap > span or offset > span:
            blocks.append(Block(start=ev.timestamp, duration=span, events=[ev]))
        else:
            cur.events.append(ev)
    return blocks


def compute_state(
    events: Iterable[UsageEvent],
    now: datetime | None = None,
    session_hours: int = 5,
) -> SessionState:
    now = now or datetime.now(tz=timezone.utc)
    span = timedelta(hours=session_hours)
    deduped = dedupe_events(events)
    blocks = build_blocks(deduped, session_hours=session_hours, now=now)

    active: Block | None = None
    for b in blocks:
        if b.start <= now <= b.end:
            active = b
            break

    is_idle = active is None
    next_reset = active.end if active else None
    by_model_active = active.by_model if active else {}

    local_today = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = local_today - timedelta(days=local_today.weekday())
    today_total = sum(e.total_tokens for e in deduped if e.timestamp >= local_today)
    week_total = sum(e.total_tokens for e in deduped if e.timestamp >= week_start)

    return SessionState(
        now=now,
        active=active,
        next_reset=next_reset,
        is_idle=is_idle,
        today_total=today_total,
        week_total=week_total,
        by_model_active=by_model_active,
        all_blocks=blocks,
    )


def format_countdown(target: datetime, now: datetime) -> str:
    delta = target - now
    if delta.total_seconds() <= 0:
        return "0m"
    total_min = int(delta.total_seconds() // 60)
    hours, mins = divmod(total_min, 60)
    if hours == 0:
        return f"{mins}m"
    return f"{hours}h{mins:02d}m"


def format_tokens_short(n: int) -> str:
    if n < 1_000:
        return str(n)
    if n < 10_000:
        return f"{n / 1_000:.1f}k"
    if n < 1_000_000:
        return f"{n / 1_000:.0f}k"
    return f"{n / 1_000_000:.2f}M"
