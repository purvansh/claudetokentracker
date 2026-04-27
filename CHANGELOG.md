# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - Unreleased

### Added
- Initial release.
- Ayatana tray indicator showing current 5-hour Claude Code session token usage and reset countdown.
- `claude-tray status` terminal summary.
- `claude-tray bar --format {json,short,tokens}` for waybar/polybar/i3blocks integration.
- `claude-tray --once --json` smoke/CI mode.
- Multi-distro one-line installer covering apt/dnf/pacman/zypper.
- systemd `--user` unit for autostart on tray-supporting desktops.
- Hot-swappable model pricing at `~/.config/claude-tray/model-pricing.json`.
- Configurable soft-cap thresholds with green/yellow/red icon states.
