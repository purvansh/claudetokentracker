#!/usr/bin/env bash
# Uninstall claude-tray. Leaves config and cache in place; prints how to remove them.
set -euo pipefail

c_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
c_green() { printf '\033[32m%s\033[0m\n' "$*"; }
c_blue()  { printf '\033[34m%s\033[0m\n' "$*"; }
c_yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }

ok()   { c_green "✔ $*"; }
info() { c_blue  "→ $*"; }
warn() { c_yellow "! $*"; }

trap 'c_red "Uninstall failed at line $LINENO."' ERR

if systemctl --user list-unit-files claude-tray.service >/dev/null 2>&1; then
  info "Stopping and disabling claude-tray.service…"
  systemctl --user disable --now claude-tray.service 2>/dev/null || true
fi

rm -f \
  "$HOME/.config/systemd/user/claude-tray.service" \
  "$HOME/.local/share/applications/claude-tray.desktop" \
  "$HOME/.config/autostart/claude-tray.desktop"

rm -f "$HOME/.local/share/icons/hicolor/symbolic/apps/"claude-tray-*-symbolic.svg \
      "$HOME/.local/share/icons/hicolor/symbolic/apps/claude-tray-symbolic.svg"
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

if command -v pipx >/dev/null 2>&1 && pipx list 2>/dev/null | grep -q "package claude-tray"; then
  info "Removing pipx package…"
  pipx uninstall claude-tray
fi

systemctl --user daemon-reload 2>/dev/null || true

ok "claude-tray removed."
warn "Config and cache were preserved. To delete them too:"
echo "  rm -rf ~/.config/claude-tray ~/.cache/claude-tray"
