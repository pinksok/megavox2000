# MegaVox 2000

**MEGA BASS DIGITAL XBS PROCESSING SYSTEM**

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

If you received an SD card with MegaVox 2000 pre-installed:

1. Insert the SD card and power on your Raspberry Pi
2. On your phone, connect to Wi-Fi network **MegaVox2000-Setup** (password: `mega2000`)
3. A setup page will appear -- select your home Wi-Fi and enter the password
4. Once connected, go to **http://mega.local** from any device on your network
5. Sign in with your Google account when prompted

**Windows users:** If prompted for a WPS PIN instead of a password, go to Settings > Network > Wi-Fi > Manage known networks, forget "MegaVox2000-Setup", and reconnect using the password `mega2000`.

## Setup from Scratch (Recommended)

Requirements: Raspberry Pi 3B/3B+ (also works on Pi 4, Pi 5), microSD card, Wi-Fi.

1. Flash **Raspberry Pi OS Lite (32-bit)** with [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
   - Select **Raspberry Pi 3** as the device
   - In settings: set hostname `mega`, username `mega`, a password, your Wi-Fi credentials, and enable SSH (password authentication)
2. Insert SD card into Pi and power on. Wait for it to connect to Wi-Fi (~1-2 minutes)
3. SSH in and install:
   ```bash
   ssh mega@mega.local
   # Add your SSH key for future access (optional):
   mkdir -p ~/.ssh && chmod 700 ~/.ssh
   echo "your-public-key-here" >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   # Install MegaVox:
   sudo apt update && sudo apt install -y git
   git clone https://github.com/pinksok/megavox2000.git
   cd megavox2000
   sudo bash install.sh
   ```
4. Add OAuth credentials (see below) and reboot: `sudo reboot`
5. Visit **http://mega.local** from any device on your network

On a new network (no saved Wi-Fi), the Pi broadcasts **MegaVox2000-Setup** -- connect and use the setup page.

**Note:** Pi 3 requires 32-bit OS. 64-bit will not boot (solid red LED, no green activity).

## Automated SD Card Prep (Alternative)

If you prefer a one-step SD card prep from Windows:

1. Flash Pi OS Lite (32-bit) with Raspberry Pi Imager (hostname `mega`, username `mega`, Wi-Fi, SSH)
2. After flashing, open Git Bash in the repo directory and run:
   ```bash
   bash prep-sd.sh E
   ```
   (Replace `E` with your SD card's drive letter. It will ask for OAuth credentials.)
3. Eject, insert into Pi, power on. Wait ~5-10 minutes for install + reboot
4. Visit **http://mega.local**

## Google Cloud Project Setup

To use YouTube Music, you need Google OAuth credentials:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the **YouTube Data API v3**
4. Go to **Credentials** > **Create Credentials** > **OAuth client ID**
5. Application type: **TVs and Limited Input devices**
6. Copy the Client ID and Client Secret
7. Add credentials using **one** of these methods:

   **Option A: From the web UI (easiest)**
   Visit `http://mega.local` -- if no credentials are configured, you'll see a form to enter your Client ID and Client Secret directly in the browser.

   **Option B: Via SSH**
   ```bash
   ssh mega@mega.local
   cat > ~/megavox2000/app/oauth_config.json << 'EOF'
   {
       "client_id": "YOUR_CLIENT_ID_HERE",
       "client_secret": "YOUR_CLIENT_SECRET_HERE"
   }
   EOF
   chmod 600 ~/megavox2000/app/oauth_config.json
   systemctl --user restart megavox2000
   ```

**Updating credentials:** If your client secret changes, you can update it anytime from the web UI -- no SSH required. The sign-in screen will show the credential form if the current credentials are invalid.

**Note:** If your Google Cloud project's OAuth consent screen is in "Testing" mode, you must add each user's Google account as a test user in the console. For broader distribution, submit for verification to switch to "Production" mode.

## Hardware

- Raspberry Pi 3 Model B/B+ (also works on Pi 4, Pi 5)
- MicroSD card (8GB minimum)
- Power supply (5V/2.5A for Pi 3)
- Audio output: 3.5mm jack, HDMI, USB audio, or Bluetooth speaker

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Can't find MegaVox2000-Setup Wi-Fi | Wait 30 seconds after power-on for the hotspot to start |
| Windows asks for WPS PIN | Forget the network, reconnect with password `mega2000` |
| No sound | Check volume in web UI; verify audio output with `aplay -l` |
| "OAuth not configured" | Enter credentials in the web UI form, or create `oauth_config.json` via SSH |
| Sign-in spins forever | Credentials may be invalid -- the UI will show the error and a form to update them |
| Page won't load | Try `http://mega.local:5000` or find the Pi's IP with `ping mega.local` |
| Playback stutters | Check Wi-Fi signal strength; try a wired Ethernet connection |

## Architecture

```
Phone/Laptop ──── Wi-Fi ────> Raspberry Pi (mega.local)
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
systemctl --user restart megavox2000

# View logs
journalctl --user -u megavox2000 -f

# Re-run Wi-Fi setup (force AP mode)
sudo systemctl restart megavox-setup

# Update yt-dlp
sudo pip3 install --break-system-packages --upgrade yt-dlp
```

## License

MIT
