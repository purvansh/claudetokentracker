"""Shared logic to compute a snapshot from disk + render terminal/JSON output."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .cache import ParseCache
from .config import Config
from .parser import discover_session_files
from .pricing import block_cost, event_cost, events_cost, load_pricing
from .session import SessionState, compute_state, format_countdown, format_tokens_short


@dataclass
class Snapshot:
    state: SessionState
    active_cost: float
    today_cost: float
    week_cost: float
    by_model_cost: dict[str, float]
    pricing_version: int


def take_snapshot(cfg: Config, *, now: datetime | None = None) -> Snapshot:
    now = now or datetime.now(tz=timezone.utc)
    cache = ParseCache.load(cfg.cache_file)
    paths = discover_session_files(cfg.claude_data_dir)
    events = cache.get_events(paths)
    cache.save()
    state = compute_state(events, now=now, session_hours=cfg.session_hours)
    pricing = load_pricing(cfg.pricing_override_path if cfg.pricing_override_path.exists() else None)
    active_cost = block_cost(state.active, pricing) if state.active else 0.0
    from datetime import timedelta
    today_cutoff = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    week_cutoff = today_cutoff - timedelta(days=today_cutoff.weekday())
    today_cost = events_cost((e for e in events if e.timestamp >= today_cutoff), pricing)
    week_cost = events_cost((e for e in events if e.timestamp >= week_cutoff), pricing)
    by_model_cost: dict[str, float] = {}
    if state.active:
        for ev in state.active.events:
            by_model_cost[ev.model] = by_model_cost.get(ev.model, 0.0) + event_cost(ev, pricing)
    return Snapshot(
        state=state,
        active_cost=active_cost,
        today_cost=today_cost,
        week_cost=week_cost,
        by_model_cost=by_model_cost,
        pricing_version=pricing.version,
    )


def snapshot_to_dict(snap: Snapshot) -> dict:
    s = snap.state
    return {
        "now": s.now.isoformat(),
        "is_idle": s.is_idle,
        "active": None
        if s.active is None
        else {
            "start": s.active.start.isoformat(),
            "end": s.active.end.isoformat(),
            "tokens": s.active.total_tokens,
            "cost": round(snap.active_cost, 4),
            "by_model": s.by_model_active,
            "by_model_cost": {k: round(v, 4) for k, v in snap.by_model_cost.items()},
        },
        "next_reset": None if s.next_reset is None else s.next_reset.isoformat(),
        "minutes_until_reset": None
        if s.next_reset is None
        else max(0, int((s.next_reset - s.now).total_seconds() // 60)),
        "today_total": s.today_total,
        "today_cost": round(snap.today_cost, 4),
        "week_total": s.week_total,
        "week_cost": round(snap.week_cost, 4),
        "pricing_version": snap.pricing_version,
    }


def print_status(cfg: Config, *, file=sys.stdout) -> int:
    snap = take_snapshot(cfg)
    s = snap.state
    out = []
    out.append("Claude Code session status")
    out.append("=" * 32)
    if s.is_idle or s.active is None:
        out.append("Active session: (idle — no events in the last %dh)" % cfg.session_hours)
    else:
        local_end = s.active.end.astimezone()
        out.append(
            f"Tokens:        {s.active.total_tokens:,}   ({format_tokens_short(s.active.total_tokens)})"
        )
        out.append(f"Cost:          ${snap.active_cost:,.2f}")
        out.append(
            f"Resets in:     {format_countdown(s.active.end, s.now)}   "
            f"(at {local_end.strftime('%H:%M %Z')})"
        )
        if s.by_model_active:
            out.append("By model:")
            for model, tok in sorted(s.by_model_active.items(), key=lambda kv: -kv[1]):
                cost = snap.by_model_cost.get(model, 0.0)
                out.append(f"  {model:<22} {tok:>12,}   ${cost:,.2f}")
    out.append("")
    out.append(f"Today:   {s.today_total:>12,}   ${snap.today_cost:,.2f}")
    out.append(f"Week:    {s.week_total:>12,}   ${snap.week_cost:,.2f}")
    print("\n".join(out), file=file)
    return 0


def print_once_json(cfg: Config, *, file=sys.stdout) -> int:
    snap = take_snapshot(cfg)
    print(json.dumps(snapshot_to_dict(snap), indent=2), file=file)
    return 0
