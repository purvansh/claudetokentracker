"""Stream Claude Code JSONL session files and yield normalized usage events."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageEvent:
    timestamp: datetime
    request_id: str
    message_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_5m: int
    cache_creation_1h: int
    cache_read: int
    service_tier: str
    source_file: str

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_5m
            + self.cache_creation_1h
            + self.cache_read
        )


def _parse_timestamp(s: str) -> datetime | None:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _coerce_token_count(d: dict, key: str, source_file: str) -> int:
    """Return an int token count from `d[key]`. Treat missing/None as 0; log unexpected types."""
    raw = d.get(key)
    if raw is None:
        return 0
    if isinstance(raw, bool):
        log.warning("unexpected bool for %s in %s; treating as 0", key, source_file)
        return 0
    if isinstance(raw, (int, float)):
        return int(raw)
    log.warning("unexpected type %s for %s in %s; treating as 0", type(raw).__name__, key, source_file)
    return 0


def parse_event_dict(d: dict, source_file: str) -> UsageEvent | None:
    if not isinstance(d, dict) or d.get("type") != "assistant":
        return None
    message = d.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    request_id = d.get("requestId") or message.get("id")
    if not request_id:
        return None
    ts = _parse_timestamp(d.get("timestamp", ""))
    if ts is None:
        return None
    cache_creation = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
    return UsageEvent(
        timestamp=ts,
        request_id=request_id,
        message_id=message.get("id", ""),
        model=message.get("model", "unknown"),
        input_tokens=_coerce_token_count(usage, "input_tokens", source_file),
        output_tokens=_coerce_token_count(usage, "output_tokens", source_file),
        cache_creation_5m=_coerce_token_count(cache_creation, "ephemeral_5m_input_tokens", source_file),
        cache_creation_1h=_coerce_token_count(cache_creation, "ephemeral_1h_input_tokens", source_file),
        cache_read=_coerce_token_count(usage, "cache_read_input_tokens", source_file),
        service_tier=str(usage.get("service_tier", "")),
        source_file=source_file,
    )


def iter_jsonl_events(path: Path, *, tolerate_last_partial: bool = True) -> Iterator[UsageEvent]:
    """Yield UsageEvent objects from a single JSONL file. Robust to partial lines."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        log.warning("could not read %s: %s", path, e)
        return
    last_idx = len(lines) - 1
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            level = logging.DEBUG if (tolerate_last_partial and i == last_idx) else logging.WARNING
            log.log(level, "skip malformed JSON in %s line %d", path, i + 1)
            continue
        ev = parse_event_dict(d, str(path))
        if ev is not None:
            yield ev


def discover_session_files(data_dir: Path) -> list[Path]:
    """Return all *.jsonl files under data_dir/*/ (Claude Code project layout)."""
    if not data_dir.exists():
        return []
    out: list[Path] = []
    try:
        for project in os.scandir(data_dir):
            if not project.is_dir(follow_symlinks=False):
                continue
            try:
                for f in os.scandir(project.path):
                    if f.is_file(follow_symlinks=False) and f.name.endswith(".jsonl"):
                        out.append(Path(f.path))
            except OSError:
                continue
    except OSError as e:
        log.warning("could not scan %s: %s", data_dir, e)
    return out


def file_stat(path: Path) -> tuple[int, int] | None:
    """Return (mtime_ns, size) or None if the file is unreadable."""
    try:
        st = path.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None
