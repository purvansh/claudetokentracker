"""mtime-keyed pickle cache for parsed UsageEvents."""
from __future__ import annotations

import logging
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .parser import UsageEvent, file_stat, iter_jsonl_events

log = logging.getLogger(__name__)

CACHE_VERSION = 2
LIVE_WINDOW_SECONDS = 60


@dataclass
class _CachedFile:
    mtime_ns: int
    size: int
    events: list[UsageEvent]


@dataclass
class ParseCache:
    cache_path: Path
    files: dict[str, _CachedFile] = field(default_factory=dict)
    version: int = CACHE_VERSION
    _dirty: bool = False

    @classmethod
    def load(cls, cache_path: Path) -> "ParseCache":
        if not cache_path.exists():
            return cls(cache_path=cache_path)
        try:
            with open(cache_path, "rb") as f:
                obj = pickle.load(f)
            if not isinstance(obj, dict) or obj.get("version") != CACHE_VERSION:
                log.info("dropping incompatible cache at %s", cache_path)
                return cls(cache_path=cache_path)
            files_raw = obj.get("files") or {}
            return cls(cache_path=cache_path, files=dict(files_raw), version=CACHE_VERSION)
        except (pickle.UnpicklingError, OSError, EOFError, AttributeError, ImportError) as e:
            log.info("could not load cache at %s (%s); starting fresh", cache_path, e)
            return cls(cache_path=cache_path)

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                pickle.dump({"version": self.version, "files": self.files}, f, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(self.cache_path)
            self._dirty = False
        except OSError as e:
            log.warning("could not save cache to %s: %s", self.cache_path, e)

    def get_events(self, paths: Iterable[Path], *, now_seconds: float | None = None) -> list[UsageEvent]:
        now_seconds = now_seconds if now_seconds is not None else time.time()
        live_threshold_ns = int((now_seconds - LIVE_WINDOW_SECONDS) * 1e9)
        seen_keys: set[str] = set()
        out: list[UsageEvent] = []
        for path in paths:
            key = str(path)
            seen_keys.add(key)
            stat = file_stat(path)
            if stat is None:
                continue
            mtime_ns, size = stat
            is_live = mtime_ns >= live_threshold_ns
            cached = self.files.get(key)
            if cached and not is_live and cached.mtime_ns == mtime_ns and cached.size == size:
                out.extend(cached.events)
                continue
            events = list(iter_jsonl_events(path))
            if not is_live:
                self.files[key] = _CachedFile(mtime_ns=mtime_ns, size=size, events=events)
                self._dirty = True
            else:
                # avoid caching live files; drop any stale cached version
                if cached is not None:
                    self.files.pop(key, None)
                    self._dirty = True
            out.extend(events)
        # purge cached entries for files that no longer exist
        for stale in [k for k in self.files if k not in seen_keys]:
            self.files.pop(stale, None)
            self._dirty = True
        return out
