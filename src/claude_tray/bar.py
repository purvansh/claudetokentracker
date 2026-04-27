"""One-line output for waybar / polybar / i3blocks."""
from __future__ import annotations

import json
import sys

from .config import Config
from .session import format_countdown, format_tokens_short
from .status import take_snapshot


def _state_class(snap, cfg: Config) -> str:
    if snap.state.is_idle or snap.state.active is None:
        return "idle"
    if cfg.display_mode == "cost":
        ratio = snap.active_cost / cfg.soft_cap_cost if cfg.soft_cap_cost else 0.0
    elif cfg.display_mode == "both":
        ratio = max(
            snap.state.active.total_tokens / cfg.soft_cap_tokens if cfg.soft_cap_tokens else 0.0,
            snap.active_cost / cfg.soft_cap_cost if cfg.soft_cap_cost else 0.0,
        )
    else:
        ratio = snap.state.active.total_tokens / cfg.soft_cap_tokens if cfg.soft_cap_tokens else 0.0
    if ratio >= 0.9:
        return "red"
    if ratio >= 0.6:
        return "yellow"
    return "green"


def _format_text(snap, cfg: Config) -> str:
    s = snap.state
    if s.is_idle or s.active is None:
        return "Claude: idle"
    countdown = format_countdown(s.active.end, s.now)
    tokens = format_tokens_short(s.active.total_tokens)
    cost = f"${snap.active_cost:,.2f}"
    if cfg.display_mode == "cost":
        return f"{cost} · {countdown}"
    if cfg.display_mode == "both":
        return f"{tokens} / {cost} · {countdown}"
    return f"{tokens} · {countdown}"


def _format_tooltip(snap, cfg: Config) -> str:
    s = snap.state
    if s.is_idle or s.active is None:
        return f"No Claude Code activity in the last {cfg.session_hours}h"
    local_end = s.active.end.astimezone().strftime("%H:%M")
    return (
        f"Tokens: {s.active.total_tokens:,}\n"
        f"Cost: ${snap.active_cost:,.2f}\n"
        f"Resets at {local_end}\n"
        f"Today: {s.today_total:,}  ${snap.today_cost:,.2f}\n"
        f"Week:  {s.week_total:,}  ${snap.week_cost:,.2f}"
    )


def print_bar(cfg: Config, fmt: str = "json", *, file=sys.stdout) -> int:
    snap = take_snapshot(cfg)
    text = _format_text(snap, cfg)
    if fmt == "short":
        print(text, file=file)
        return 0
    if fmt == "tokens":
        if snap.state.active:
            print(snap.state.active.total_tokens, file=file)
        else:
            print(0, file=file)
        return 0
    klass = _state_class(snap, cfg)
    if snap.state.active:
        if cfg.display_mode == "cost":
            pct = int(min(100, 100 * snap.active_cost / cfg.soft_cap_cost)) if cfg.soft_cap_cost else 0
        else:
            pct = int(min(100, 100 * snap.state.active.total_tokens / cfg.soft_cap_tokens)) if cfg.soft_cap_tokens else 0
    else:
        pct = 0
    payload = {
        "text": text,
        "tooltip": _format_tooltip(snap, cfg),
        "class": klass,
        "percentage": pct,
    }
    print(json.dumps(payload), file=file)
    return 0
