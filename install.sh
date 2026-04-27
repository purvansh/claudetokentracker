#!/usr/bin/env bash
# claude-tray installer — Linux desktop tray indicator for Claude Code session usage.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/your-username/claude-tray/main/install.sh | bash
# or, from a clone:
#   ./install.sh

set -euo pipefail

REPO_URL="${CLAUDE_TRAY_REPO_URL:-https://github.com/your-username/claude-tray}"
PYPI_NAME="${CLAUDE_TRAY_PYPI_NAME:-claude-tray}"
INSTALL_FROM="${CLAUDE_TRAY_INSTALL_FROM:-pypi}"   # pypi | local | git

# ----- helpers ---------------------------------------------------------------

c_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
c_green() { printf '\033[32m%s\033[0m\n' "$*"; }
c_blue()  { printf '\033[34m%s\033[0m\n' "$*"; }
c_yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }

bail() { c_red "✖ $*"; exit 1; }
ok()   { c_green "✔ $*"; }
info() { c_blue  "→ $*"; }
warn() { c_yellow "! $*"; }

trap 'c_red "Install failed at line $LINENO. See the message above for the cause."' ERR

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || bail "$1 is required but not installed."
}

# ----- detect package manager ------------------------------------------------

detect_pm() {
  if command -v apt >/dev/null 2>&1;    then echo apt
  elif command -v dnf >/dev/null 2>&1;  then echo dnf
  elif command -v pacman >/dev/null 2>&1; then echo pacman
  elif command -v zypper >/dev/null 2>&1; then echo zypper
  else echo none
  fi
}

install_system_deps() {
  local pm=$1
  info "Installing system dependencies via $pm…"
  case "$pm" in
    apt)
      sudo apt update
      sudo apt install -y \
        gir1.2-ayatanaappindicator3-0.1 \
        python3-gi \
        gir1.2-gtk-3.0 \
        pipx
      ;;
    dnf)
      sudo dnf install -y \
        libayatana-appindicator-gtk3 \
        python3-gobject \
        pipx
      ;;
    pacman)
      sudo pacman -S --needed --noconfirm \
        libayatana-appindicator \
        python-gobject \
        python-pipx
      ;;
    zypper)
      sudo zypper install -y \
        typelib-1_0-AyatanaAppIndicator3-0_1 \
        python3-gobject \
        python3-pipx
      ;;
    none)
      bail "Could not detect a supported package manager (apt/dnf/pacman/zypper).
Install these system packages manually then re-run this installer with CLAUDE_TRAY_SKIP_DEPS=1:
  - Ayatana AppIndicator 3 typelib
  - PyGObject (python3-gi / python-gobject)
  - GTK 3 typelib
  - pipx"
      ;;
  esac
  ok "System dependencies installed."
}

# ----- detect desktop / session ---------------------------------------------

is_tiling_wm() {
  case "${XDG_CURRENT_DESKTOP:-}${XDG_SESSION_DESKTOP:-}${DESKTOP_SESSION:-}" in
    *Hyprland*|*sway*|*i3*|*river*|*niri*) return 0 ;;
    *) return 1 ;;
  esac
}

is_tray_de() {
  case "${XDG_CURRENT_DESKTOP:-}" in
    *GNOME*|*KDE*|*XFCE*|*X-Cinnamon*|*MATE*|*Unity*|*LXQt*|*Pantheon*|*Budgie*) return 0 ;;
    *) return 1 ;;
  esac
}

check_appindicator_extension() {
  if ! command -v gnome-shell >/dev/null 2>&1; then return 0; fi
  case "${XDG_CURRENT_DESKTOP:-}" in *GNOME*) ;; *) return 0 ;; esac
  if command -v gnome-extensions >/dev/null 2>&1; then
    if ! gnome-extensions list 2>/dev/null | grep -qi appindicator; then
      warn "GNOME detected but no AppIndicator extension is enabled."
      warn "Install: https://extensions.gnome.org/extension/615/appindicator-support/"
    fi
  fi
}

# ----- install ---------------------------------------------------------------

install_pipx_package() {
  info "Installing $PYPI_NAME via pipx (with --system-site-packages so it can reach PyGObject)…"
  pipx ensurepath >/dev/null 2>&1 || true

  case "$INSTALL_FROM" in
    pypi)
      pipx install --system-site-packages --force "$PYPI_NAME"
      ;;
    local)
      local script_dir
      script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
      pipx install --system-site-packages --force "$script_dir"
      ;;
    git)
      pipx install --system-site-packages --force "git+$REPO_URL.git"
      ;;
    *)
      bail "Unknown CLAUDE_TRAY_INSTALL_FROM=$INSTALL_FROM (use pypi|local|git)"
      ;;
  esac
  ok "claude-tray installed at $(command -v claude-tray 2>/dev/null || echo "$HOME/.local/bin/claude-tray")"
}

install_assets() {
  info "Installing desktop entry, icons, and systemd unit…"
  local prefix_app="$HOME/.local/share/applications"
  local prefix_auto="$HOME/.config/autostart"
  local prefix_icons="$HOME/.local/share/icons/hicolor/symbolic/apps"
  local prefix_systemd="$HOME/.config/systemd/user"

  mkdir -p "$prefix_app" "$prefix_auto" "$prefix_icons" "$prefix_systemd"

  # Locate bundled assets — works for both `local` install and `pypi` install.
  local script_dir asset_dir icon_src
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -d "$script_dir/assets" ]]; then
    asset_dir="$script_dir/assets"
  else
    asset_dir=""
  fi

  # Desktop entry — try repo asset first; otherwise generate from scratch.
  if [[ -n "$asset_dir" && -f "$asset_dir/claude-tray.desktop" ]]; then
    cp "$asset_dir/claude-tray.desktop" "$prefix_app/claude-tray.desktop"
  else
    cat >"$prefix_app/claude-tray.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=Claude Tray
Comment=Claude Code 5-hour session usage indicator
Exec=claude-tray
Icon=claude-tray-symbolic
Terminal=false
Categories=Utility;GTK;
StartupNotify=false
X-GNOME-Autostart-enabled=true
DESK
  fi
  cp "$prefix_app/claude-tray.desktop" "$prefix_auto/claude-tray.desktop"

  # Icons — copy from python package install location (pipx venv) so they stay in sync.
  local pkg_data
  pkg_data="$(claude-tray --version >/dev/null 2>&1 && \
    python3 - <<'PY' 2>/dev/null
import importlib.resources, pathlib, sys
try:
    p = importlib.resources.files("claude_tray.data.icons")
    print(p)
except Exception:
    sys.exit(1)
PY
)"
  if [[ -n "${pkg_data:-}" && -d "$pkg_data" ]]; then
    icon_src="$pkg_data"
  elif [[ -n "$asset_dir" && -d "$script_dir/src/claude_tray/data/icons" ]]; then
    icon_src="$script_dir/src/claude_tray/data/icons"
  else
    icon_src=""
  fi

  if [[ -n "$icon_src" ]]; then
    cp -f "$icon_src"/claude-tray-*.svg "$prefix_icons/" 2>/dev/null || true
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
      gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    fi
  else
    warn "Could not locate bundled icons; the indicator will fall back to a system icon."
  fi

  # systemd unit
  if [[ -n "$asset_dir" && -f "$asset_dir/claude-tray.service" ]]; then
    cp "$asset_dir/claude-tray.service" "$prefix_systemd/claude-tray.service"
  else
    cat >"$prefix_systemd/claude-tray.service" <<'UNIT'
[Unit]
Description=Claude Code session tray indicator
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
ExecStart=%h/.local/bin/claude-tray
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=graphical-session.target
UNIT
  fi
  ok "Desktop, autostart, icons, and systemd unit installed."
}

start_service() {
  if is_tiling_wm; then
    warn "Tiling WM detected (Hyprland/sway/i3/…). System tray indicators don't render here."
    info "Use claude-tray bar mode in your status bar instead. Example for waybar:"
    cat <<'WAYBAR'
  "custom/claude": {
    "exec": "claude-tray bar --format json",
    "interval": 30,
    "return-type": "json"
  }
WAYBAR
    return
  fi

  if ! is_tray_de; then
    warn "Unknown desktop (\${XDG_CURRENT_DESKTOP:-not set}). Skipping systemd auto-start."
    info "Run claude-tray manually to verify, then enable autostart:  systemctl --user enable --now claude-tray"
    return
  fi

  info "Enabling systemd --user service…"
  systemctl --user daemon-reload
  systemctl --user enable --now claude-tray.service
  ok "claude-tray.service is running."
}

# ----- main ------------------------------------------------------------------

main() {
  c_blue "==> claude-tray installer"

  if [[ -z "${CLAUDE_TRAY_SKIP_DEPS:-}" ]]; then
    local pm
    pm="$(detect_pm)"
    install_system_deps "$pm"
  else
    info "CLAUDE_TRAY_SKIP_DEPS set — skipping system package installation."
    require_cmd pipx
  fi

  install_pipx_package
  install_assets
  check_appindicator_extension
  start_service

  c_green "
✔ claude-tray installed.

Try it:
  claude-tray status                  # one-shot terminal summary
  claude-tray --once --json           # JSON snapshot
  claude-tray bar --format json       # output for waybar/polybar
  systemctl --user status claude-tray # service status

Config: ~/.config/claude-tray/config.toml
Logs:   ~/.cache/claude-tray/claude-tray.log

Uninstall:  $REPO_URL/blob/main/uninstall.sh
"
}

main "$@"
