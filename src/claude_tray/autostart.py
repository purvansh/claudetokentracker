"""Manage XDG desktop entries for the apps menu and login autostart."""
from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

log = logging.getLogger(__name__)

APP_ID = "claude-tray"
ENTRY_NAME = f"{APP_ID}.desktop"
APPS_DIR = Path(os.path.expanduser("~/.local/share/applications"))
AUTOSTART_DIR = Path(os.path.expanduser("~/.config/autostart"))


def _exec_command() -> str:
    bin_path = shutil.which("claude-tray")
    if bin_path:
        return bin_path
    pkg_dir = Path(__file__).resolve().parent
    if pkg_dir.parent.name == "src":
        return f"/usr/bin/env PYTHONPATH={pkg_dir.parent} {sys.executable} -m claude_tray run"
    return f"{sys.executable} -m claude_tray run"


def _desktop_entry_text() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Claude Tray\n"
        "Comment=Claude Code 5-hour session usage indicator\n"
        f"Exec={_exec_command()}\n"
        "Icon=claude-tray-symbolic\n"
        "Terminal=false\n"
        "Categories=Utility;GTK;\n"
        "StartupNotify=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def apps_entry_path() -> Path:
    return APPS_DIR / ENTRY_NAME


def autostart_entry_path() -> Path:
    return AUTOSTART_DIR / ENTRY_NAME


def ensure_apps_entry() -> None:
    """Ensure the desktop entry exists in the apps menu so users can launch it."""
    try:
        APPS_DIR.mkdir(parents=True, exist_ok=True)
        text = _desktop_entry_text()
        path = apps_entry_path()
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
    except OSError as e:
        log.warning("could not write apps entry %s: %s", apps_entry_path(), e)


def is_autostart_enabled() -> bool:
    return autostart_entry_path().exists()


def set_autostart(enabled: bool) -> None:
    path = autostart_entry_path()
    if enabled:
        try:
            AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(_desktop_entry_text(), encoding="utf-8")
        except OSError as e:
            log.warning("could not enable autostart at %s: %s", path, e)
            raise
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            log.warning("could not remove autostart %s: %s", path, e)
            raise
