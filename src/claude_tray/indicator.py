"""Ayatana tray indicator — the user-facing GTK component.

Imported lazily so that `claude-tray status` and `claude-tray bar` work on
machines without GTK/Ayatana installed (e.g. headless CI, tiling WMs).
"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
from importlib.resources import as_file, files
from pathlib import Path

from . import autostart
from .config import Config
from .session import format_countdown, format_tokens_short
from .status import take_snapshot

log = logging.getLogger(__name__)


def _import_gtk():
    """Lazy import of GTK + Ayatana. Raises ImportError with a friendly message."""
    import gi

    try:
        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
    except ValueError as e:
        raise ImportError(
            "GTK / AyatanaAppIndicator3 typelibs not found. Install:\n"
            "  Debian/Ubuntu: sudo apt install gir1.2-ayatanaappindicator3-0.1 python3-gi gir1.2-gtk-3.0\n"
            "  Fedora/RHEL:   sudo dnf install libayatana-appindicator-gtk3 python3-gobject\n"
            "  Arch:          sudo pacman -S libayatana-appindicator python-gobject\n"
            "  openSUSE:      sudo zypper install typelib-1_0-AyatanaAppIndicator3-0_1 python3-gobject"
        ) from e

    from gi.repository import AyatanaAppIndicator3, GLib, Gtk  # type: ignore

    return AyatanaAppIndicator3, GLib, Gtk


def _stage_icons(cfg: Config) -> Path:
    """Copy bundled SVG icons into the cache dir so they have stable paths."""
    target = cfg.cache_dir / "icons"
    target.mkdir(parents=True, exist_ok=True)
    for name in (
        "claude-tray-symbolic.svg",
        "claude-tray-green-symbolic.svg",
        "claude-tray-yellow-symbolic.svg",
        "claude-tray-red-symbolic.svg",
    ):
        with as_file(files("claude_tray.data.icons").joinpath(name)) as src:
            data = Path(src).read_bytes()
            (target / name).write_bytes(data)
    return target


class TrayIndicator:
    APP_ID = "claude-tray"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.AppInd, self.GLib, self.Gtk = _import_gtk()
        self.icon_dir = _stage_icons(cfg)
        self.indicator = self.AppInd.Indicator.new(
            self.APP_ID,
            str(self.icon_dir / "claude-tray-symbolic.svg"),
            self.AppInd.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(self.AppInd.IndicatorStatus.ACTIVE)
        self.indicator.set_icon_theme_path(str(self.icon_dir))
        self.indicator.set_title("Claude Tray")
        self._last_snapshot = None
        self.menu = self.Gtk.Menu()
        self.indicator.set_menu(self.menu)
        autostart.ensure_apps_entry()
        self._refresh()

    # ---------- formatting ----------
    def _label_text(self, snap) -> str:
        s = snap.state
        if s.is_idle or s.active is None:
            return "Claude: idle"
        countdown = format_countdown(s.active.end, s.now)
        tokens = format_tokens_short(s.active.total_tokens)
        cost = f"${snap.active_cost:,.2f}"
        if self.cfg.display_mode == "cost":
            return f"{cost} · {countdown}"
        if self.cfg.display_mode == "both":
            return f"{tokens} / {cost} · {countdown}"
        return f"{tokens} · {countdown}"

    def _icon_name(self, snap) -> str:
        s = snap.state
        if s.is_idle or s.active is None:
            return "claude-tray-symbolic"
        if self.cfg.display_mode == "cost":
            ratio = snap.active_cost / self.cfg.soft_cap_cost if self.cfg.soft_cap_cost else 0.0
        elif self.cfg.display_mode == "both":
            ratio = max(
                s.active.total_tokens / self.cfg.soft_cap_tokens if self.cfg.soft_cap_tokens else 0.0,
                snap.active_cost / self.cfg.soft_cap_cost if self.cfg.soft_cap_cost else 0.0,
            )
        else:
            ratio = (
                s.active.total_tokens / self.cfg.soft_cap_tokens if self.cfg.soft_cap_tokens else 0.0
            )
        if ratio >= 0.9:
            return "claude-tray-red-symbolic"
        if ratio >= 0.6:
            return "claude-tray-yellow-symbolic"
        return "claude-tray-green-symbolic"

    # ---------- menu ----------
    def _build_menu(self, snap) -> None:
        Gtk = self.Gtk
        for child in self.menu.get_children():
            self.menu.remove(child)
        s = snap.state

        def add(label: str, *, sensitive: bool = True, callback=None):
            item = Gtk.MenuItem(label=label)
            item.set_sensitive(sensitive)
            if callback is not None:
                item.connect("activate", callback)
            self.menu.append(item)
            return item

        def add_sep():
            self.menu.append(Gtk.SeparatorMenuItem())

        if s.is_idle or s.active is None:
            add(f"Idle — no activity in last {self.cfg.session_hours}h", sensitive=False)
        else:
            add(f"Tokens: {s.active.total_tokens:,}", sensitive=False)
            add(f"Cost:   ${snap.active_cost:,.2f}", sensitive=False)
            local_end = s.active.end.astimezone().strftime("%H:%M")
            add(
                f"Resets in {format_countdown(s.active.end, s.now)}  (at {local_end})",
                sensitive=False,
            )
            if self.cfg.show_model_breakdown and s.by_model_active:
                add_sep()
                add("By model:", sensitive=False)
                for model, tok in sorted(s.by_model_active.items(), key=lambda kv: -kv[1]):
                    cost = snap.by_model_cost.get(model, 0.0)
                    add(f"  {model}: {format_tokens_short(tok)}  ${cost:,.2f}", sensitive=False)
        add_sep()
        add(
            f"Today: {format_tokens_short(s.today_total)}  ${snap.today_cost:,.2f}",
            sensitive=False,
        )
        add(
            f"Week:  {format_tokens_short(s.week_total)}  ${snap.week_cost:,.2f}",
            sensitive=False,
        )
        add_sep()
        add("Refresh now", callback=lambda _i: self._refresh())
        add("Open config…", callback=lambda _i: self._xdg_open(self.cfg.config_path))
        add("View logs…", callback=lambda _i: self._xdg_open(self.cfg.log_file))

        autostart_item = Gtk.CheckMenuItem(label="Start at login")
        autostart_item.set_active(autostart.is_autostart_enabled())
        autostart_item.connect("toggled", self._on_toggle_autostart)
        self.menu.append(autostart_item)

        add(f"About claude-tray", callback=self._on_about)
        add_sep()
        add("Quit", callback=lambda _i: self.Gtk.main_quit())
        self.menu.show_all()

    def _on_toggle_autostart(self, item) -> None:
        try:
            autostart.set_autostart(item.get_active())
        except OSError:
            log.exception("toggle autostart failed")
            item.handler_block_by_func(self._on_toggle_autostart)
            item.set_active(autostart.is_autostart_enabled())
            item.handler_unblock_by_func(self._on_toggle_autostart)

    # ---------- handlers ----------
    def _on_about(self, _item) -> None:
        from . import __version__

        Gtk = self.Gtk
        dlg = Gtk.AboutDialog()
        dlg.set_program_name("claude-tray")
        dlg.set_version(__version__)
        dlg.set_comments("Claude Code 5-hour session usage indicator.")
        dlg.set_license_type(Gtk.License.MIT_X11)
        dlg.run()
        dlg.destroy()

    def _xdg_open(self, path: Path) -> None:
        try:
            resolved = Path(path).expanduser().resolve()
            subprocess.Popen(
                ["xdg-open", str(resolved)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            log.warning("xdg-open %s failed: %s", path, e)

    # ---------- refresh ----------
    def _refresh(self) -> bool:
        try:
            snap = take_snapshot(self.cfg)
        except Exception:  # pragma: no cover - never let GTK timeout die
            log.exception("refresh failed")
            return True
        self._last_snapshot = snap
        try:
            self.indicator.set_label(self._label_text(snap), "Claude")
            self.indicator.set_icon_full(self._icon_name(snap), "claude-tray")
        except Exception:  # pragma: no cover
            log.exception("indicator update failed")
        self._build_menu(snap)
        return True

    # ---------- main loop ----------
    def run(self) -> None:
        self.GLib.timeout_add_seconds(self.cfg.refresh_seconds, self._refresh)
        self.Gtk.main()


def warn_if_no_tray() -> None:
    """Best-effort: warn the user if no StatusNotifierWatcher is registered on DBus."""
    if os.environ.get("CLAUDE_TRAY_SKIP_WATCHER_CHECK"):
        return
    try:
        result = subprocess.run(
            ["gdbus", "introspect", "--session", "--dest", "org.kde.StatusNotifierWatcher",
             "--object-path", "/StatusNotifierWatcher", "--only-properties"],
            capture_output=True, timeout=2, text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return
    if result.returncode != 0:
        log.warning(
            "No system tray host detected on DBus. On GNOME, install the AppIndicator extension: "
            "https://extensions.gnome.org/extension/615/appindicator-support/"
        )
        try:
            subprocess.Popen(
                ["notify-send", "claude-tray",
                 "No system tray host detected. On GNOME install the AppIndicator extension."],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass


def run_indicator(cfg: Config) -> int:
    warn_if_no_tray()
    ind = TrayIndicator(cfg)
    try:
        ind.run()
    except KeyboardInterrupt:
        pass
    return 0


# Used by --once to avoid pulling in GTK at all.
def take_once(cfg: Config) -> dict:
    from .status import snapshot_to_dict

    return snapshot_to_dict(take_snapshot(cfg, now=datetime.now(tz=timezone.utc)))
