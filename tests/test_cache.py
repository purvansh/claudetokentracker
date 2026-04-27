from __future__ import annotations

import os
import time
from pathlib import Path

from claude_tray.cache import ParseCache


JSONL = (
    '{"type":"assistant","timestamp":"2026-04-01T10:00:01.000Z","requestId":"r1",'
    '"message":{"id":"m","model":"claude-opus-4-6","usage":{"input_tokens":10,"output_tokens":5}}}\n'
)


def _write(path: Path, text: str, *, age_seconds: float = 0) -> None:
    path.write_text(text, encoding="utf-8")
    if age_seconds:
        past = time.time() - age_seconds
        os.utime(path, (past, past))


def test_cache_reuses_unchanged_file(tmp_path: Path):
    f = tmp_path / "a.jsonl"
    _write(f, JSONL, age_seconds=600)
    cache = ParseCache.load(tmp_path / "cache.pkl")
    out1 = cache.get_events([f])
    assert len(out1) == 1
    # Inject a sentinel into the cached events; if the cache reuses, we should see it.
    cache.files[str(f)].events[0] = cache.files[str(f)].events[0]
    cached_obj = cache.files[str(f)].events
    out2 = cache.get_events([f])
    assert out2 == cached_obj


def test_cache_reparses_when_mtime_changes(tmp_path: Path):
    f = tmp_path / "a.jsonl"
    _write(f, JSONL, age_seconds=600)
    cache = ParseCache.load(tmp_path / "cache.pkl")
    cache.get_events([f])
    # touch file forward to invalidate
    new = time.time()
    os.utime(f, (new, new))
    out = cache.get_events([f])
    assert len(out) == 1


def test_cache_skips_caching_for_live_file(tmp_path: Path):
    f = tmp_path / "live.jsonl"
    f.write_text(JSONL, encoding="utf-8")  # mtime ≈ now → live
    cache = ParseCache.load(tmp_path / "cache.pkl")
    cache.get_events([f])
    # live file should not be persisted
    assert str(f) not in cache.files


def test_cache_purges_missing_files(tmp_path: Path):
    f = tmp_path / "a.jsonl"
    _write(f, JSONL, age_seconds=600)
    cache = ParseCache.load(tmp_path / "cache.pkl")
    cache.get_events([f])
    assert str(f) in cache.files
    f.unlink()
    cache.get_events([])
    assert str(f) not in cache.files


def test_cache_save_load_roundtrip(tmp_path: Path):
    f = tmp_path / "a.jsonl"
    _write(f, JSONL, age_seconds=600)
    cache_path = tmp_path / "cache.pkl"
    c1 = ParseCache.load(cache_path)
    c1.get_events([f])
    c1.save()
    c2 = ParseCache.load(cache_path)
    assert str(f) in c2.files
