# claude-tray

A lightweight Linux tray indicator that shows your live Claude Code 5-hour session usage — tokens, cost, model breakdown, and reset countdown — by reading the JSONL session logs Claude Code writes to `~/.claude/projects/`.

Works on tray-supporting desktops (GNOME, KDE, XFCE, Cinnamon, MATE) via Ayatana AppIndicator. Includes a `bar` mode for waybar/polybar/i3blocks on tiling window managers.

## Features

- **Live session usage** — current 5-hour rolling window, updated every 30s.
- **Tokens, cost, or both** — choose what's displayed in the tray label.
- **Model breakdown** — see which model (Opus / Sonnet / Haiku / etc.) is using your budget.
- **Today & this-week totals** — at a glance from the menu.
- **Soft caps with color states** — icon turns yellow at 60% and red at 90% of your configured cap.
- **Bar mode** — `claude-tray bar --format json` for waybar/polybar/i3blocks.
- **Start at login** — toggle from the tray menu, no terminal required.
- **Hot-swappable pricing** — drop a JSON file at `~/.config/claude-tray/model-pricing.json` to override defaults.

## Install

### One-line installer (recommended)

```bash
git clone <this-repo> claude-tray
cd claude-tray
CLAUDE_TRAY_INSTALL_FROM=local ./install.sh
```

The installer detects your distro (apt / dnf / pacman / zypper), installs the GTK + Ayatana system packages, sets up `claude-tray` via `pipx`, registers desktop entries, and enables a systemd `--user` service for autostart.

### Manual install

System packages (one of):

```bash
# Debian / Ubuntu
sudo apt install gir1.2-ayatanaappindicator3-0.1 python3-gi gir1.2-gtk-3.0 pipx

# Fedora / RHEL
sudo dnf install libayatana-appindicator-gtk3 python3-gobject pipx

# Arch
sudo pacman -S libayatana-appindicator python-gobject python-pipx

# openSUSE
sudo zypper install typelib-1_0-AyatanaAppIndicator3-0_1 python3-gobject python3-pipx
```

Then:

```bash
pipx install --system-site-packages .
claude-tray            # launch the tray
```

The `--system-site-packages` flag is required so the pipx venv can see the system-installed PyGObject (it isn't on PyPI).

### From source (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
PYTHONPATH=src python -m claude_tray run
```

> **Dependencies:** runtime deps live in `pyproject.toml` (`tomli` only, on Python < 3.11). No `requirements.txt` is needed — use `pip install .` or `pip install -e '.[dev]'`. GTK + Ayatana are system packages, not pip-installable.

## Usage

```
claude-tray                              # launch the tray indicator (default)
claude-tray status                       # one-shot terminal summary
claude-tray --once --json                # JSON snapshot for scripts
claude-tray bar --format json            # waybar payload
claude-tray bar --format short           # plain text for polybar/i3blocks
claude-tray bar --format tokens          # just the integer token count
```

Common flags:

```
-v, --verbose         enable DEBUG logging
--config PATH         use a non-default config.toml
--data-dir PATH       override claude_data_dir
```

### Tray menu

Right-click the tray icon for:

- **Tokens / Cost / Resets in** — current session info
- **By model** — per-model breakdown
- **Today / Week** — running totals
- **Refresh now** — force a re-scan
- **Open config…** — opens `~/.config/claude-tray/config.toml`
- **View logs…** — opens `~/.cache/claude-tray/claude-tray.log`
- **Start at login** ☑ — toggle XDG autostart (creates/removes `~/.config/autostart/claude-tray.desktop`)
- **Quit**

### waybar example

```jsonc
"custom/claude": {
  "exec": "claude-tray bar --format json",
  "interval": 30,
  "return-type": "json"
}
```

The JSON payload includes `text`, `tooltip`, `class` (`idle`/`green`/`yellow`/`red`), and `percentage`.

## Configuration

Config lives at `~/.config/claude-tray/config.toml` and is auto-created on first run with defaults. The indicator picks up changes on its next refresh — no restart needed.

```toml
refresh_seconds      = 30           # how often to re-scan ~/.claude/projects (min: 5)
session_hours        = 5            # length of the rolling rate-limit window
display_mode         = "tokens"     # "tokens" | "cost" | "both"
soft_cap_tokens      = 200000       # icon turns yellow >=60% / red >=90%
soft_cap_cost        = 5.0          # used when display_mode = "cost" or "both"
claude_data_dir      = "~/.claude/projects"
show_model_breakdown = true
icon_theme           = "symbolic"   # "symbolic" | "color"
log_level            = "INFO"
```

### Custom pricing

If a model isn't in the built-in pricing table (or rates change), drop a JSON file at `~/.config/claude-tray/model-pricing.json`:

```json
{
  "version": 2,
  "models": {
    "claude-opus-4-7": {
      "input":  15.0,
      "output": 75.0,
      "cache_read":  1.5,
      "cache_creation_5m": 18.75,
      "cache_creation_1h": 30.0
    }
  }
}
```

All values are USD per million tokens.

## Troubleshooting

### "GTK / AyatanaAppIndicator3 typelibs not found"

You're missing the system packages. See the [Install](#install) section. After installing, **log out and back in** so the new typelibs are picked up.

### Tray icon doesn't appear (GNOME)

Vanilla GNOME doesn't have a system tray. Install the AppIndicator extension:

> https://extensions.gnome.org/extension/615/appindicator-support/

### Tray icon doesn't appear (tiling WMs — Hyprland, sway, i3, river, niri)

Tiling WMs typically don't host a system tray. Use **bar mode** in your status bar instead — see the [waybar example](#waybar-example).

### "No system tray host detected on DBus"

The indicator started but no tray host is registered. On GNOME this means the AppIndicator extension is missing or disabled. On other desktops, ensure your panel is running.

### Numbers don't match Claude.ai's session %

The tray reads **only** Claude Code CLI usage from local JSONL logs in `~/.claude/projects/`. Claude.ai web usage and Claude API usage are tracked server-side and aren't visible to this tool. Anthropic's "% used" on the web also appears to be cost-weighted, not raw tokens, so the numbers won't line up exactly even if you only use the CLI.

### Logs

```
~/.cache/claude-tray/claude-tray.log
```

Run `claude-tray -v status` for verbose stderr output.

### Reset everything

```bash
./uninstall.sh
rm -rf ~/.config/claude-tray ~/.cache/claude-tray
```

## How it works

Claude Code writes one JSONL file per session to `~/.claude/projects/<path-encoded-cwd>/<uuid>.jsonl`. Each `assistant` event includes a `usage` block with `input_tokens`, `output_tokens`, `cache_creation`, and `cache_read_input_tokens`.

claude-tray:

1. Discovers all JSONL files under `~/.claude/projects/`.
2. Parses `assistant` events with a tolerant JSONL reader (handles partial last lines from a live session).
3. Caches parsed events keyed on `(mtime, size)` to avoid re-parsing on every refresh.
4. Groups events into rolling 5-hour blocks using the same algorithm as [`ccusage`](https://github.com/ryoppippi/ccusage).
5. Picks the block containing "now" as the active session and computes tokens + cost (per-model rates).

## Development

```bash
pip install -e '.[dev]'
pytest                          # run the test suite (31 tests)
ruff check src/ tests/          # lint
```

Project layout:

```
src/claude_tray/
  __main__.py        # argparse dispatcher
  config.py          # TOML config + validation
  parser.py          # JSONL → UsageEvent
  session.py         # 5-hour block grouping (ccusage rules)
  pricing.py         # per-model cost computation
  cache.py           # mtime+size keyed parse cache
  status.py          # snapshot composition + terminal output
  bar.py             # waybar/polybar/i3blocks output
  indicator.py       # GTK + Ayatana tray (lazy-imported)
  autostart.py       # XDG desktop entries (apps menu + autostart)
  logging_setup.py   # file + stderr logging
  data/icons/        # bundled SVG icons
```

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

- 5-hour block algorithm follows [ccusage](https://github.com/ryoppippi/ccusage).
- Built on Ayatana AppIndicator + GTK 3 via PyGObject.
