"""Per-model pricing tables (USD per million tokens)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Iterable

from .parser import UsageEvent
from .session import Block

log = logging.getLogger(__name__)

_MTOK = 1_000_000.0


@dataclass(frozen=True)
class ModelPricing:
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float


@dataclass
class PricingTable:
    version: int
    updated: str
    models: dict[str, ModelPricing]
    aliases: dict[str, str]
    _warned_unknown: set[str]

    def for_model(self, model: str) -> ModelPricing | None:
        canon = self.aliases.get(model, model)
        if canon in self.models:
            return self.models[canon]
        if model in self.models:
            return self.models[model]
        if model not in self._warned_unknown:
            log.warning("no pricing for model %r; treating as $0", model)
            self._warned_unknown.add(model)
        return None


def _load_json(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("could not load pricing override %s: %s", path, e)
        return None


def _from_dict(d: dict) -> PricingTable:
    models_raw = d.get("models", {}) or {}
    models = {
        name: ModelPricing(
            input=float(p.get("input", 0)),
            output=float(p.get("output", 0)),
            cache_read=float(p.get("cache_read", 0)),
            cache_write_5m=float(p.get("cache_write_5m", 0)),
            cache_write_1h=float(p.get("cache_write_1h", 0)),
        )
        for name, p in models_raw.items()
    }
    return PricingTable(
        version=int(d.get("version", 0)),
        updated=str(d.get("updated", "")),
        models=models,
        aliases=dict(d.get("model_aliases", {}) or {}),
        _warned_unknown=set(),
    )


def load_pricing(override_path: Path | None = None) -> PricingTable:
    bundled_text = files("claude_tray.data").joinpath("model-pricing.json").read_text(encoding="utf-8")
    bundled = json.loads(bundled_text)
    override = _load_json(override_path)
    if override:
        merged = dict(bundled)
        merged_models = dict(bundled.get("models") or {})
        merged_models.update(override.get("models") or {})
        merged_aliases = dict(bundled.get("model_aliases") or {})
        merged_aliases.update(override.get("model_aliases") or {})
        merged["models"] = merged_models
        merged["model_aliases"] = merged_aliases
        merged["version"] = override.get("version", merged.get("version"))
        merged["updated"] = override.get("updated", merged.get("updated"))
        return _from_dict(merged)
    return _from_dict(bundled)


def event_cost(event: UsageEvent, table: PricingTable) -> float:
    p = table.for_model(event.model)
    if p is None:
        return 0.0
    return (
        event.input_tokens * p.input
        + event.output_tokens * p.output
        + event.cache_read * p.cache_read
        + event.cache_creation_5m * p.cache_write_5m
        + event.cache_creation_1h * p.cache_write_1h
    ) / _MTOK


def block_cost(block: Block, table: PricingTable) -> float:
    return sum(event_cost(e, table) for e in block.events)


def events_cost(events: Iterable[UsageEvent], table: PricingTable) -> float:
    return sum(event_cost(e, table) for e in events)
