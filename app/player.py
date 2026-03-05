"""Playback control: yt-dlp resolution, ffplay lifecycle, PulseAudio."""

import subprocess
import os
import signal
import threading
import time

import config
import state
from history import log_to_history


def yt_dlp_base_args():
    """Return common yt-dlp args for audio URL resolution."""
    return ["yt-dlp", "--js-runtimes", "node"]


def _parse_duration(s):
    """Parse a duration string (seconds or HH:MM:SS) to integer seconds."""
    try:
        return int(float(s))
    except (ValueError, TypeError):
        pass
    try:
        parts = s.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, TypeError, AttributeError):
        pass
    return 0


def _pulse_env():
    """Return PulseAudio environment dict with dynamic UID."""
    uid = os.getuid()
    return {
        "PULSE_SERVER": "unix:/run/user/{}/pulse/native".format(uid),
        "XDG_RUNTIME_DIR": "/run/user/{}".format(uid),
        "PATH": os.environ.get("PATH", "/usr/bin"),
    }


def _check_is_live(url):
    """Quick check if a URL is a live stream using yt-dlp metadata."""
    try:
        result = subprocess.run(
            yt_dlp_base_args() + [
                "--no-playlist", "--skip-download",
                "--print", "%(is_live)s",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip().lower() == "true"
    except Exception:
        pass
    return False


def resolve_url(url):
    """Use yt-dlp to get direct audio URL, title, thumbnail, and duration."""
    try:
        result = subprocess.run(
            yt_dlp_base_args() + [
                "-f", "bestaudio/best",
                "--no-playlist",
                "-g",
                "--get-title",
                "--get-thumbnail",
                "--get-duration",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if result.returncode != 0:
            result = subprocess.run(
                yt_dlp_base_args() + [
                    "--no-playlist",
                    "-g",
                    "--get-title",
                    "--get-thumbnail",
                    "--get-duration",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=45,
            )
        if result.returncode != 0:
            err = result.stderr.strip()
            for line in err.splitlines():
                if "ERROR" in line:
                    return None, None, None, line.split("ERROR: ", 1)[-1], 0, False
            return None, None, None, err or "yt-dlp failed", 0, False
        lines = result.stdout.strip().splitlines()
        # Output order: title, URL, thumbnail, duration
        if len(lines) >= 4:
            duration = _parse_duration(lines[3])
            is_live = _check_is_live(url) if duration == 0 else False
            return lines[1], lines[0], lines[2], None, duration, is_live
        elif len(lines) >= 3:
            is_live = _check_is_live(url)
            return lines[1], lines[0], lines[2], None, 0, is_live
        elif len(lines) >= 2:
            return lines[1], lines[0], None, None, 0, False
        elif len(lines) == 1:
            return lines[0], url, None, None, 0, False
        else:
            return None, None, None, "No audio URL returned", 0, False
    except subprocess.TimeoutExpired:
        return None, None, None, "URL resolution timed out", 0, False
    except Exception as e:
        return None, None, None, str(e), 0, False


def fetch_playlist(playlist_url, offset=0, limit=20):
    """Fetch tracks from a YouTube playlist/feed with thumbnails."""
    start = offset + 1
    end = offset + limit
    try:
        result = subprocess.run(
            yt_dlp_base_args() + [
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s",
                "-I", "{}:{}".format(start, end),
                playlist_url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            for line in err.splitlines():
                if "ERROR" in line:
                    return None, line.split("ERROR: ", 1)[-1]
            return None, err or "Failed to fetch playlist"
        tracks = []
        for line in result.stdout.strip().splitlines():
            if "\t" in line:
                parts = line.split("\t")
                if len(parts) >= 2:
                    vid_id, title = parts[0], parts[1]
                    thumbnail = "https://i.ytimg.com/vi/{}/mqdefault.jpg".format(vid_id)
                else:
                    continue
                if vid_id and title:
                    tracks.append({"id": vid_id, "title": title, "thumbnail": thumbnail})
        return tracks, None
    except subprocess.TimeoutExpired:
        return None, "Request timed out"
    except Exception as e:
        return None, str(e)


def _get_our_sink_input(env):
    """Find the PulseAudio sink-input ID belonging to our ffplay process."""
    if not state.player_process:
        return None
    our_pid = state.player_process.pid
    try:
        result = subprocess.run(
            ["pactl", "list", "sink-inputs"],
            capture_output=True, text=True, timeout=5, env=env,
        )
        current_idx = None
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Sink Input #"):
                current_idx = line.split("#")[1]
            if "application.process.id" in line and '"' in line:
                pid_str = line.split('"')[1]
                try:
                    if int(pid_str) == our_pid:
                        return current_idx
                except ValueError:
                    pass
    except Exception:
        pass
    return None


def _get_all_sink_inputs_short(env):
    """Get all sink input IDs (fallback if PID matching fails)."""
    try:
        result = subprocess.run(
            ["pactl", "list", "sink-inputs", "short"],
            capture_output=True, text=True, timeout=5, env=env,
        )
        ids = []
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if parts:
                ids.append(parts[0])
        return ids
    except Exception:
        return []


def _mute_sink(env, sink_id, mute):
    """Mute or unmute a specific sink input."""
    val = "1" if mute else "0"
    if sink_id:
        try:
            subprocess.run(
                ["pactl", "set-sink-input-mute", sink_id, val],
                timeout=5, env=env,
            )
        except Exception:
            pass
    else:
        for sid in _get_all_sink_inputs_short(env):
            try:
                subprocess.run(
                    ["pactl", "set-sink-input-mute", sid, val],
                    timeout=5, env=env,
                )
            except Exception:
                pass


def watch_player(proc, generation):
    """Monitor player process and capture errors when it exits."""
    proc.wait()
    with state.player_lock:
        # Only update state if this watcher is still for the current generation
        if state.play_generation != generation:
            return
        state.loading = False
        if proc.returncode not in (0, -9, -15):
            try:
                with open(config.LOG_FILE, "r") as f:
                    log_content = f.read()
                if log_content.strip():
                    for line in reversed(log_content.strip().splitlines()):
                        line = line.strip()
                        if line and "M-A:" not in line:
                            state.last_error = line[:200]
                            break
                else:
                    state.last_error = "Playback failed (exit code {})".format(proc.returncode)
            except Exception:
                state.last_error = "Playback failed (exit code {})".format(proc.returncode)


def start_playback(url):
    """Resolve URL and start ffplay in a background thread."""
    with state.player_lock:
        my_generation = state.play_generation

    audio_url, title, thumbnail, error, duration, is_live = resolve_url(url)

    with state.player_lock:
        if state.play_generation != my_generation:
            return
        if error:
            state.last_error = error
            state.loading = False
            return

    # Log to local playback history
    from services import get_service
    svc = get_service()
    if svc:
        track_id = svc.parse_track_id(url)
        if track_id:
            log_to_history(track_id, title or url, thumbnail or "")

    env = os.environ.copy()
    pulse = _pulse_env()
    env["PULSE_SERVER"] = pulse["PULSE_SERVER"]
    env["XDG_RUNTIME_DIR"] = pulse["XDG_RUNTIME_DIR"]

    log_fh = open(config.LOG_FILE, "w")

    cmd = [
        "ffplay",
        "-nodisp",
        "-vn",
        "-framedrop",
        "-sync", "audio",
    ]
    if is_live:
        cmd += ["-infbuf"]
    else:
        cmd += ["-autoexit"]
    cmd += [
        "-analyzeduration", "500000",
        "-probesize", "1000000",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        audio_url,
    ]

    with state.player_lock:
        if state.play_generation != my_generation:
            log_fh.close()
            return

        state.current_title = title or url
        state.current_thumbnail = thumbnail or ""
        state.paused = False
        state.is_live = is_live

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=log_fh,
            stderr=log_fh,
            env=env,
            preexec_fn=os.setsid,
        )
        state.player_process = proc
        state.current_audio_url = audio_url
        state.current_duration = duration
        state.playback_start_time = time.time()
        state.playback_elapsed = 0

    # Unmute our specific sink input once it appears
    def _unmute_new_stream():
        pulse_env = _pulse_env()
        for _ in range(10):
            time.sleep(0.3)
            with state.player_lock:
                if state.play_generation != my_generation:
                    return
            sink_id = _get_our_sink_input(pulse_env)
            if sink_id:
                _mute_sink(pulse_env, sink_id, False)
                return
        # Fallback: unmute all if we can't find ours by PID
        _mute_sink(_pulse_env(), None, False)

    threading.Thread(target=_unmute_new_stream, daemon=True).start()

    watcher = threading.Thread(target=watch_player, args=(proc, my_generation), daemon=True)
    watcher.start()


def _kill_proc(proc, was_paused=False):
    """Kill a process group, resuming first if paused."""
    try:
        if was_paused:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGCONT)
            except Exception:
                pass
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGCONT)
        except Exception:
            pass
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=3)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=2)
        except Exception:
            pass


def stop_player():
    """Kill ffplay process, unmute if paused, reset state."""
    with state.player_lock:
        state.play_generation += 1
        state.loading = False
        was_paused = state.paused
        state.paused = False
        proc = state.player_process
        state.player_process = None
        feeder = state.live_feeder
        state.live_feeder = None
        state.current_audio_url = ""
        state.current_duration = 0
        state.playback_start_time = 0
        state.playback_elapsed = 0
        state.is_live = False

    if proc:
        _kill_proc(proc, was_paused)
    if feeder:
        _kill_proc(feeder)


def seek_to(position):
    """Seek to a position (seconds) by restarting ffplay with -ss."""
    with state.player_lock:
        audio_url = state.current_audio_url
        if not audio_url or not state.player_process:
            return False
        duration = state.current_duration
        title = state.current_title
        thumbnail = state.current_thumbnail

    if position < 0:
        position = 0
    if duration and position > duration:
        position = duration

    # Kill current ffplay
    _kill_current_player()

    env = os.environ.copy()
    pulse = _pulse_env()
    env["PULSE_SERVER"] = pulse["PULSE_SERVER"]
    env["XDG_RUNTIME_DIR"] = pulse["XDG_RUNTIME_DIR"]

    log_fh = open(config.LOG_FILE, "w")

    cmd = [
        "ffplay",
        "-nodisp",
        "-vn",
        "-framedrop",
        "-sync", "audio",
        "-autoexit",
        "-ss", str(position),
        "-analyzeduration", "500000",
        "-probesize", "1000000",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        audio_url,
    ]

    with state.player_lock:
        state.current_title = title
        state.current_thumbnail = thumbnail
        state.current_audio_url = audio_url
        state.current_duration = duration
        state.paused = False
        state.last_error = ""
        state.loading = False

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=log_fh,
            stderr=log_fh,
            env=env,
            preexec_fn=os.setsid,
        )
        state.player_process = proc
        state.playback_elapsed = position
        state.playback_start_time = time.time()
        my_generation = state.play_generation

    # Unmute new stream
    def _unmute():
        pulse_env = _pulse_env()
        for _ in range(10):
            time.sleep(0.3)
            with state.player_lock:
                if state.play_generation != my_generation:
                    return
            sink_id = _get_our_sink_input(pulse_env)
            if sink_id:
                _mute_sink(pulse_env, sink_id, False)
                return
        _mute_sink(_pulse_env(), None, False)

    threading.Thread(target=_unmute, daemon=True).start()
    threading.Thread(target=watch_player, args=(proc, my_generation), daemon=True).start()
    return True


def _kill_current_player():
    """Kill the current ffplay process without resetting playback metadata."""
    with state.player_lock:
        was_paused = state.paused
        proc = state.player_process
        state.player_process = None
        feeder = state.live_feeder
        state.live_feeder = None

    if proc:
        _kill_proc(proc, was_paused)
    if feeder:
        _kill_proc(feeder)


def toggle_pause_internal():
    """Toggle pause state - shared by web UI and BT button."""
    with state.player_lock:
        if not state.player_process or state.player_process.poll() is not None:
            return
        env = _pulse_env()
        if state.paused:
            os.killpg(os.getpgid(state.player_process.pid), signal.SIGCONT)
            state.paused = False
            state.playback_start_time = time.time()
            sink_id = _get_our_sink_input(env)
            _mute_sink(env, sink_id, False)
        else:
            sink_id = _get_our_sink_input(env)
            _mute_sink(env, sink_id, True)
            os.killpg(os.getpgid(state.player_process.pid), signal.SIGSTOP)
            state.paused = True
            if state.playback_start_time:
                state.playback_elapsed += time.time() - state.playback_start_time
                state.playback_start_time = 0
    update_mpris_state()


def update_mpris_state():
    """Push current playback state to MPRIS so mpris-proxy relays it to BT speaker."""
    try:
        import dbus
        bus = dbus.SessionBus()
        obj = bus.get_object("org.mpris.MediaPlayer2.megavox2000",
                             "/org/mpris/MediaPlayer2")
        props_iface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        new_status = "Paused" if state.paused else "Playing"
        props_iface.Set("org.mpris.MediaPlayer2.Player", "PlaybackStatus", new_status)
    except Exception:
        pass
