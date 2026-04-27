"""CLI entrypoint: argparse dispatcher for indicator / status / bar / --once."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .logging_setup import setup_logging


def _common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-v", "--verbose", action="store_true", help="Enable DEBUG logging to stderr")
    p.add_argument("--config", type=Path, default=None, help="Path to config.toml")
    p.add_argument("--data-dir", type=Path, default=None, help="Override claude_data_dir")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="claude-tray",
        description="Linux tray indicator for your current Claude Code 5-hour session usage.",
    )
    p.add_argument("--version", action="version", version=f"claude-tray {__version__}")
    p.add_argument("--once", action="store_true", help="Print one snapshot and exit (with --json)")
    p.add_argument("--json", action="store_true", help="Used with --once: emit JSON")
    _common_args(p)

    sub = p.add_subparsers(dest="command")

    sp_status = sub.add_parser("status", help="Print a human-readable summary and exit")
    _common_args(sp_status)

    sp_bar = sub.add_parser("bar", help="Print a one-line status (waybar/polybar/i3blocks)")
    sp_bar.add_argument(
        "--format", choices=["json", "short", "tokens"], default="json",
        help="Output format (default: json for waybar)",
    )
    _common_args(sp_bar)

    sp_run = sub.add_parser("run", help="Run the tray indicator (default if no subcommand)")
    _common_args(sp_run)

    return p


def _resolve_cfg(ns: argparse.Namespace):
    cfg = load_config(getattr(ns, "config", None))
    if getattr(ns, "data_dir", None):
        cfg.claude_data_dir = Path(os.path.expanduser(str(ns.data_dir)))
    setup_logging(cfg.log_file, level=cfg.log_level, verbose=getattr(ns, "verbose", False))
    return cfg


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    cfg = _resolve_cfg(ns)

    if ns.once:
        from .status import take_snapshot, snapshot_to_dict, print_status
        if ns.json:
            print(json.dumps(snapshot_to_dict(take_snapshot(cfg)), indent=2))
            return 0
        return print_status(cfg)

    cmd = ns.command or "run"
    if cmd == "status":
        from .status import print_status
        return print_status(cfg)
    if cmd == "bar":
        from .bar import print_bar
        return print_bar(cfg, ns.format)
    if cmd == "run":
        try:
            from .indicator import run_indicator
        except ImportError as e:
            print(f"claude-tray: cannot start indicator: {e}", file=sys.stderr)
            return 2
        return run_indicator(cfg)

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
