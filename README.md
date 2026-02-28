# Magnavox 2000

A retro-styled music player for Raspberry Pi. Stream music through your home speakers with a web-based remote control you can use from any phone or computer.

**Currently supported:** YouTube Music
**Coming soon:** Spotify, Pandora

## What It Does

Power on your Pi, connect it to your Wi-Fi through the setup screen, then control your music from any device on your network. Features include:

- Browse your YouTube Music library (liked songs, playlists)
- Search and play any YouTube video as audio
- Retro terminal-style UI with equalizer visualizer
- Bluetooth speaker support with hardware button controls
- Auto-resume playback after reboot
- Volume control from the web UI

## Quick Start (Pre-Built Image)

If you received an SD card with Magnavox 2000 pre-installed:

1. Insert the SD card and power on your Raspberry Pi
2. On your phone, connect to Wi-Fi network **Magnavox2000-Setup** (password: `magnavox2000`)
3. A setup page will appear -- select your home Wi-Fi and enter the password
4. Once connected, go to **http://boombox.local** from any device on your network
5. Sign in with your Google account when prompted

**Windows users:** If prompted for a WPS PIN instead of a password, go to Settings > Network > Wi-Fi > Manage known networks, forget "Magnavox2000-Setup", and reconnect using the password `magnavox2000`.

## Install From Scratch

Requirements: Raspberry Pi 3B/3B+ (also works on Pi 4, Pi 5) running Raspberry Pi OS Lite (Bookworm or later).

```bash
# Clone the repo
git clone https://github.com/pinksok/magnavox2000.git
cd magnavox2000

# Run the installer
sudo bash install.sh
```

The installer will:
- Install all system and Python dependencies
- Set up the application and systemd services
- Set the hostname to `boombox`
- Configure Wi-Fi onboarding hotspot

After installation, add your OAuth credentials (see below) and reboot.

## Google Cloud Project Setup

To use YouTube Music, you need Google OAuth credentials:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the **YouTube Data API v3**
4. Go to **Credentials** > **Create Credentials** > **OAuth client ID**
5. Application type: **TVs and Limited Input devices**
6. Copy the Client ID and Client Secret
7. Create the config file on your Pi:

```bash
cat > ~/magnavox2000/app/oauth_config.json << 'EOF'
{
    "client_id": "YOUR_CLIENT_ID_HERE",
    "client_secret": "YOUR_CLIENT_SECRET_HERE"
}
EOF
chmod 600 ~/magnavox2000/app/oauth_config.json
```

8. Reboot: `sudo reboot`

**Note:** If your Google Cloud project's OAuth consent screen is in "Testing" mode, you must add each user's Google account as a test user in the console. For broader distribution, submit for verification to switch to "Production" mode.

## Hardware

- Raspberry Pi 3 Model B/B+ (also works on Pi 4, Pi 5)
- MicroSD card (8GB minimum)
- Power supply (5V/2.5A for Pi 3)
- Audio output: 3.5mm jack, HDMI, USB audio, or Bluetooth speaker

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Can't find Magnavox2000-Setup Wi-Fi | Wait 30 seconds after power-on for the hotspot to start |
| Windows asks for WPS PIN | Forget the network, reconnect with password `magnavox2000` |
| No sound | Check volume in web UI; verify audio output with `aplay -l` |
| "OAuth not configured" | Create `oauth_config.json` -- see setup instructions above |
| Page won't load | Try `http://boombox.local:5000` or find the Pi's IP with `ping boombox.local` |
| Playback stutters | Check Wi-Fi signal strength; try a wired Ethernet connection |

## Architecture

```
Phone/Laptop ──── Wi-Fi ────> Raspberry Pi (boombox.local)
                                  │
                                  ├── Flask web server (:5000)
                                  ├── yt-dlp (audio URL resolution)
                                  ├── ffplay (audio playback)
                                  └── PulseAudio/PipeWire (audio output)
```

The app uses a service provider pattern -- YouTube is the first implemented service, with Spotify and Pandora stubs ready for future development.

## Service Management

```bash
# Restart the player
systemctl --user restart magnavox2000

# View logs
journalctl --user -u magnavox2000 -f

# Re-run Wi-Fi setup (force AP mode)
sudo systemctl restart magnavox-setup

# Update yt-dlp
sudo pip3 install --break-system-packages --upgrade yt-dlp
```

## License

MIT
