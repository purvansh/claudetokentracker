"""TOML config at ~/.config/claude-tray/config.toml."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

log = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path.home() / ".claude" / "projects"
DEFAULT_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "claude-tray"
DEFAULT_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "claude-tray"


@dataclass
class Config:
    refresh_seconds: int = 30
    session_hours: int = 5
    display_mode: str = "tokens"  # "tokens" | "cost" | "both"
    soft_cap_tokens: int = 200_000
    soft_cap_cost: float = 5.0
    claude_data_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR)
    show_model_breakdown: bool = True
    icon_theme: str = "symbolic"
    log_level: str = "INFO"
    config_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG_DIR)
    cache_dir: Path = field(default_factory=lambda: DEFAULT_CACHE_DIR)

    @property
    def config_path(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def pricing_override_path(self) -> Path:
        return self.config_dir / "model-pricing.json"

    @property
    def cache_file(self) -> Path:
        return self.cache_dir / "parse-cache.pickle"

    @property
    def log_file(self) -> Path:
        return self.cache_dir / "claude-tray.log"


_VALID_DISPLAY = {"tokens", "cost", "both"}
_VALID_ICON_THEMES = {"symbolic", "color"}


def _coerce(name: str, value: Any, default: Any) -> Any:
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            log.warning("config %s: expected int, got %r; using default %r", name, value, default)
            return default
    if isinstance(default, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            log.warning("config %s: expected float, got %r; using default %r", name, value, default)
            return default
    if isinstance(default, Path):
        return Path(os.path.expanduser(str(value)))
    return value


DEFAULT_TOML = """\
# claude-tray configuration. Edit and the indicator picks up changes on its next refresh.

refresh_seconds      = 30           # how often to re-scan ~/.claude/projects
session_hours        = 5            # length of the rolling rate-limit window
display_mode         = "tokens"     # "tokens" | "cost" | "both"
soft_cap_tokens      = 200000       # icon turns yellow >=60% / red >=90% of this
soft_cap_cost        = 5.0          # used when display_mode = "cost" or "both"
claude_data_dir      = "~/.claude/projects"
show_model_breakdown = true
icon_theme           = "symbolic"   # "symbolic" | "color"
log_level            = "INFO"
"""


def write_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    path.write_text(DEFAULT_TOML, encoding="utf-8")


def load_config(path: Path | None = None) -> Config:
    cfg = Config()
    target = path or cfg.config_path
    write_default_config(target)
    try:
        with open(target, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        log.warning("could not read %s: %s; using defaults", target, e)
        return cfg

    field_names = {f.name for f in fields(Config)}
    for key, value in data.items():
        if key not in field_names:
            log.warning("config: unknown key %r ignored", key)
            continue
        default = getattr(cfg, key)
        if key == "display_mode" and value not in _VALID_DISPLAY:
            log.warning("config display_mode=%r invalid; using %r", value, default)
            continue
        if key == "icon_theme" and value not in _VALID_ICON_THEMES:
            log.warning("config icon_theme=%r invalid; using %r", value, default)
            continue
        setattr(cfg, key, _coerce(key, value, default))

    cfg.claude_data_dir = Path(os.path.expanduser(str(cfg.claude_data_dir)))
    _validate(cfg)
    cfg.config_dir.mkdir(parents=True, exist_ok=True)
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def _validate(cfg: Config) -> None:
    """Clamp invalid numeric config values to safe minimums and warn."""
    if cfg.refresh_seconds < 5:
        log.warning("config refresh_seconds=%s too low; clamping to 5", cfg.refresh_seconds)
        cfg.refresh_seconds = 5
    if cfg.session_hours < 1:
        log.warning("config session_hours=%s invalid; clamping to 1", cfg.session_hours)
        cfg.session_hours = 1
    if cfg.soft_cap_tokens <= 0:
        log.warning("config soft_cap_tokens=%s invalid; resetting to 200000", cfg.soft_cap_tokens)
        cfg.soft_cap_tokens = 200_000
    if cfg.soft_cap_cost <= 0:
        log.warning("config soft_cap_cost=%s invalid; resetting to 5.0", cfg.soft_cap_cost)
        cfg.soft_cap_cost = 5.0
