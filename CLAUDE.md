# MegaVox 2000 - Development Guide

## Project Overview

Headless music player for Raspberry Pi with web-based control interface. Branded as "MegaVox 2000 - Mega Bass Digital XBS Processing System" with a retro 90s terminal aesthetic. Supports multiple music services via a provider abstraction layer.

**Active services**: YouTube Music (fully implemented), Spotify (stub), Pandora (stub).
**Auth**: Google OAuth2 device flow with QR code. YouTube Data API v3 for library. yt-dlp for audio.
**Distribution**: Pre-built SD card images for end users, install script for developers.

## Branches

- **`main`** -- Production branch. Targets Raspberry Pi 3. No Bluetooth UI. Ships on SD card images.
- **`dev`** -- Development branch. Targets Raspberry Pi 5. Includes Bluetooth MPRIS and connect UI.

## Repository Structure

```
megavox2000/
├── app/                         # Application code
│   ├── app.py                   # Flask server, routes, captive portal, service registration
│   ├── config.py                # Paths, constants (BASE_DIR-relative)
│   ├── state.py                 # Shared mutable playback state
│   ├── history.py               # Local playback history
│   ├── player.py                # yt-dlp, ffplay, PulseAudio control
│   ├── mpris.py                 # MPRIS D-Bus for Bluetooth buttons (dev branch only)
│   ├── services.py              # Service registry/dispatcher
│   ├── service_youtube.py       # YouTube adapter (direct API v3, reads oauth_config.json)
│   ├── service_spotify.py       # Spotify adapter (stub)
│   ├── service_pandora.py       # Pandora adapter (stub)
│   ├── auth.py                  # Auth route dispatcher
│   ├── library.py               # Library route dispatcher
│   ├── wifi_setup.py            # Wi-Fi onboarding Blueprint
│   ├── favicon.svg              # Browser icon
│   ├── oauth_config.json.example
│   └── templates/
│       ├── index.html           # Main web UI
│       └── setup.html           # Wi-Fi setup captive portal
├── system/                      # Systemd and boot config (templates)
│   ├── megavox2000.service      # User service template
│   ├── megavox-setup.service    # System boot service template
│   ├── megavox-boot.sh          # Boot script template
│   └── captive-portal.conf      # DNS hijack for AP mode
├── install.sh                   # Full setup script
├── build-image.md               # SD card image build instructions
├── README.md                    # End-user documentation
├── LICENSE                      # MIT
└── .gitignore
```

## Key Design Decisions

### No hardcoded secrets
OAuth credentials are loaded from `app/oauth_config.json` (gitignored). For SD card images, credentials are baked in during image build but never committed to git.

### YouTube Data API v3 (not ytmusicapi)
ytmusicapi's OAuth is broken (HTTP 400 on all calls). We bypass it entirely and call YouTube Data API v3 directly with `requests`. Search still uses ytmusicapi unauthenticated (no quota cost). yt-dlp handles audio URL resolution without auth.

### BASE_DIR-relative paths
All runtime files (history.json, volume.json, service.json, oauth.json) are stored relative to the app directory using `os.path.dirname(os.path.abspath(__file__))`. No hardcoded home directory paths.

### Dynamic UID
PulseAudio environment uses `os.getuid()` instead of hardcoded UID 1000. Works regardless of which user runs the service.

### Pi 3 optimized (main branch)
- ffplay: `-analyzeduration 500000 -probesize 1000000` (reduced from Pi 5 values)
- yt-dlp: 45s timeout (increased from 30s for slower CPU)
- yt-dlp path: `yt-dlp` (PATH resolution, not hardcoded `/usr/local/bin/`)

### Live stream support (WIP -- NOT WORKING)
Live YouTube streams (live radio channels) are detected via `_check_is_live()` in `player.py`. The frontend shows a "LIVE" indicator, disables seeking, and skips auto-next. However, **live audio playback itself does not work** -- ffplay with `-infbuf` on a Pi 3 cannot reliably stream live content. Needs a fundamentally different approach (mpv, buffering proxy, or format transcoding).

#### yt-dlp pitfalls (do NOT repeat these)
- **Never use `-j` for URL resolution** -- the JSON `url` field is not a playable direct URL. Always use `-g`.
- **Never mix `-g`/`--get-*` with `--print`** -- output line order becomes unpredictable.
- **yt-dlp `--get-*` output order**: title first, then URL (from `-g`), then thumbnail, then duration -- despite `-g` being listed first in the command.

### Service templates
System service files use `INSTALL_DIR_PLACEHOLDER` and `INSTALL_UID_PLACEHOLDER` markers that `install.sh` replaces with actual values via `sed`.

## Service Provider Pattern

Each music service is a Python module (`service_*.py`) implementing:
```python
SERVICE_NAME = "youtube"
SERVICE_DISPLAY_NAME = "YouTube"
is_authenticated() -> bool
auth_status() -> dict
auth_start() -> dict
auth_complete() -> dict
get_liked(offset, limit) -> dict
get_playlists() -> dict
get_playlist_tracks(id, offset, limit) -> dict
search(query, limit) -> dict
build_url(track_id) -> str
parse_track_id(url) -> str | None
```

## Adding a New Music Service

1. Create `app/service_<name>.py` following the protocol above
2. Import and register it in `app/app.py`: `services.register(service_<name>)`
3. Frontend, auth routes, and library routes automatically support it

## Color Scheme

```css
--primary-green: #6a9955;      /* Text, borders, accents */
--dark-green: #4a6a4a;         /* Borders, buttons */
--cyan: #7ac5cd;               /* Now playing text */
--red: #c24848;                /* Errors, visualizer top */
--black: #000;                 /* Background */
--dark-gray: #1a1a1a;          /* Panel backgrounds */
```

## Network & Hostname

- **Hostname**: `mega` (set by install.sh)
- **Port redirect**: iptables 80 -> 5000 (set by boot service)
- **AP mode**: "MegaVox2000-Setup" hotspot, password: mega2000, WPS disabled
- **Captive portal**: DNS hijack via dnsmasq config + Flask before_request handler for OS probes
- **Mode file**: `/tmp/megavox-mode` ("ap" or "client")

## Planned Feature: SPI Display for Cassette Window

### Overview
Add-on physical display mounted in the boombox cassette deck window (2.5" x 1" opening). Shows track info and real-time spectrum analyzer. Standalone service — no changes to existing MegaVox codebase required.

### Hardware
- **Display**: BuyDisplay 2.25" bar-type IPS TFT LCD, 76x284 pixels, ST7789P3 driver, SPI interface (~$5)
  - Active area: 14.8mm x 55.3mm (0.58" x 2.18") — fits inside the 2.5" x 1" cassette window
  - Board size: 30mm x 63mm (1.18" x 2.48")
  - Mounted landscape (284px horizontal, 76px vertical)
  - Sources: [BuyDisplay](https://www.buydisplay.com/spi-tft-2-25-lcd-76x284-display-module-st7789-breakout-board-for-arduino-raspberry-pi), [Amazon](https://www.amazon.com/Display-Screen-76x284-Long-Strip-Interface/dp/B0FBW9T8FS)

### GPIO Wiring
| Display Pin | Pi GPIO | Pi Physical Pin |
|---|---|---|
| VCC | 3.3V | Pin 1 |
| GND | GND | Pin 6 |
| SCL/SCLK | GPIO 11 | Pin 23 |
| SDA/MOSI | GPIO 10 | Pin 19 |
| CS | GPIO 8 | Pin 24 |
| DC/RS | GPIO 25 | Pin 22 |
| RST | GPIO 24 | Pin 18 |
| BL | GPIO 18 (or 3.3V for always-on) | Pin 12 |

### Software Stack
- **Display rendering**: `luma.lcd` or `spidev` + `Pillow` for frame rendering
- **Spectrum data**: C.A.V.A. (Console-based Audio Visualizer for ALSA) in raw output mode, taps into PipeWire
- **Display service**: Standalone Python script as its own systemd user service
  - Polls `/status` endpoint for track title, artist, elapsed time
  - Reads C.A.V.A. raw output for spectrum bars
  - Shows scanning/loading animation (matching web UI) during track load

### Display Layout (76px tall x 284px wide)
```
┌──────────────────────────────────────────┐
│  TRACK TITLE SCROLLING...          12:34 │  (~16px)
│  Artist Name                             │  (~12px)
│  ▁ ▃ ▅ ▇ █ ▅ ▃ ▁ ▃ ▇ █ ▅ ▃ ▁ ▃ ▅ ▇ █ │  (~44px)
│                                          │  (~4px padding)
└──────────────────────────────────────────┘
```

### Additional Dependencies
```bash
# System packages:
cava

# pip packages:
luma.lcd Pillow
```

### Integration Notes
- No changes to app.py, player.py, or index.html needed
- Display service reads from existing `/status` API endpoint
- SPI must be enabled: `sudo raspi-config` → Interface Options → SPI
- Runs as a separate systemd user service (e.g., `megavox-display.service`)

## Important Notes

- **Never commit oauth_config.json** -- contains OAuth client credentials
- **Never commit oauth.json** -- contains user tokens
- **Test before committing** -- restart service and verify
- **WorkingDirectory is critical** -- the systemd service must set `WorkingDirectory` to the `app/` directory for Python imports to work

## Dependencies

```bash
# System packages:
python3-flask python3-dbus python3-gi python3-requests ffmpeg
pipewire pipewire-pulse wireplumber nodejs

# pip packages:
yt-dlp qrcode ytmusicapi

# Dev branch only (Bluetooth):
bluetooth bluez-tools
```

## Service Management

```bash
systemctl --user restart megavox2000
systemctl --user status megavox2000
journalctl --user -u megavox2000 -f
sudo systemctl restart megavox-setup   # Re-run Wi-Fi check
```

## Git Workflow

```bash
cd /home/beau/megavox2000
git add -A
git commit -m "description

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
git push origin main
```

**Git user**: pinksok (pinksok@users.noreply.github.com)
**Remote**: git@github.com:pinksok/megavox2000.git (SSH)
