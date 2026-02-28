"""YouTube Music service adapter using ytmusicapi (InnerTube API)."""

import os
import json as json_mod
import time

from ytmusicapi import YTMusic, OAuthCredentials

import state

SERVICE_NAME = "youtube"
SERVICE_DISPLAY_NAME = "YouTube"

# OAuth credentials loaded from config file (never hardcoded)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OAUTH_CONFIG_FILE = os.path.join(_BASE_DIR, "oauth_config.json")
OAUTH_FILE = os.path.join(_BASE_DIR, "oauth.json")


def _load_oauth_config():
    """Load OAuth client credentials from config file."""
    if not os.path.exists(OAUTH_CONFIG_FILE):
        return None, None
    try:
        with open(OAUTH_CONFIG_FILE) as f:
            data = json_mod.load(f)
        client_id = data.get("client_id", "")
        client_secret = data.get("client_secret", "")
        if client_id and client_secret:
            return client_id, client_secret
    except Exception:
        pass
    return None, None


_client_id, _client_secret = _load_oauth_config()
_credentials = OAuthCredentials(client_id=_client_id, client_secret=_client_secret) if _client_id else None
_ytmusic = None  # Lazily initialized YTMusic instance


# --- Internal helpers ---

def _get_ytmusic():
    """Get or create an authenticated YTMusic instance."""
    global _ytmusic
    if _ytmusic is not None:
        return _ytmusic
    if not _credentials:
        return None
    if not os.path.exists(OAUTH_FILE):
        return None
    try:
        # Check if token has correct scope (youtube.readonly won't work)
        with open(OAUTH_FILE) as f:
            token_data = json_mod.load(f)
        token_scope = token_data.get("scope", "")
        if "youtube.readonly" in token_scope:
            print("[AUTH] Token has youtube.readonly scope, needs re-auth for ytmusicapi", flush=True)
            return None
        _ytmusic = YTMusic(OAUTH_FILE, oauth_credentials=_credentials)
        return _ytmusic
    except Exception as e:
        print("[YTM] Failed to create YTMusic instance: {}".format(e), flush=True)
        return None


def _invalidate_ytmusic():
    """Clear cached YTMusic instance (call after re-auth)."""
    global _ytmusic
    _ytmusic = None


def _extract_track(item):
    """Convert a ytmusicapi track dict to our standard format."""
    vid_id = item.get("videoId", "")
    if not vid_id:
        return None
    title = item.get("title", "Unknown")
    artists = item.get("artists")
    if artists and isinstance(artists, list) and artists[0].get("name"):
        title = "{} - {}".format(artists[0]["name"], title)
    thumb = ""
    thumbnails = item.get("thumbnails")
    if thumbnails and isinstance(thumbnails, list):
        thumb = thumbnails[-1].get("url", "")
    if not thumb:
        thumb = "https://i.ytimg.com/vi/{}/mqdefault.jpg".format(vid_id)
    return {"id": vid_id, "title": title, "thumbnail": thumb}


# --- Auth protocol ---

def is_authenticated():
    return _get_ytmusic() is not None


def auth_status():
    if not _credentials:
        return {"authenticated": False, "error": "OAuth not configured. See README for setup instructions."}
    return {"authenticated": is_authenticated()}


def auth_start():
    if not _credentials:
        return {"error": "OAuth not configured. Place oauth_config.json in the app directory. See README for instructions."}
    try:
        code = _credentials.get_code()
        return {
            "url": code["verification_url"],
            "user_code": code["user_code"],
            "device_code": code["device_code"],
        }
    except Exception as e:
        return {"error": str(e)}


def auth_complete():
    if not _credentials:
        return {"error": "OAuth not configured."}
    if not state.auth_pending:
        return {"error": "No auth flow in progress. Start auth first."}
    try:
        token_data = _credentials.token_from_code(state.auth_pending["device_code"])

        # token_from_code returns error dict when pending/slow_down
        if "error" in token_data:
            error_type = token_data["error"]
            if error_type == "authorization_pending":
                return {"error": "Still waiting for authorization. Please complete sign-in on your device."}
            if error_type == "slow_down":
                return {"error": "Please wait a moment before trying again."}
            return {"error": "Auth failed: {}".format(token_data.get("error_description", str(token_data)))}

        # Success — add expires_at and save with restrictive permissions
        token_data["expires_at"] = int(time.time()) + token_data.get("expires_in", 3600)

        fd = os.open(OAUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json_mod.dump(dict(token_data), f, indent=2)

        _invalidate_ytmusic()
        print("[AUTH] OAuth token saved successfully", flush=True)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


# --- Library protocol ---

def get_liked(offset=0, limit=20):
    try:
        yt = _get_ytmusic()
        if not yt:
            return {"error": "Not authenticated"}

        total_needed = offset + limit
        result = yt.get_liked_songs(limit=total_needed)

        all_tracks = result.get("tracks", [])
        page = all_tracks[offset:offset + limit]

        tracks = []
        for item in page:
            t = _extract_track(item)
            if t:
                tracks.append(t)

        has_more = len(all_tracks) > offset + limit
        return {"tracks": tracks, "has_more": has_more}
    except Exception as e:
        return {"error": str(e)}


def get_playlists():
    try:
        yt = _get_ytmusic()
        if not yt:
            return {"error": "Not authenticated"}

        raw_playlists = yt.get_library_playlists(limit=None)

        playlists = []
        for item in raw_playlists:
            pl_id = item.get("playlistId", "")
            if not pl_id:
                continue
            title = item.get("title", "Unknown")
            thumb = ""
            thumbnails = item.get("thumbnails")
            if thumbnails and isinstance(thumbnails, list):
                thumb = thumbnails[-1].get("url", "")
            count_val = item.get("count")
            try:
                count = int(count_val) if count_val else 0
            except (ValueError, TypeError):
                count = 0
            playlists.append({"id": pl_id, "title": title, "thumbnail": thumb, "count": count})

        return {"playlists": playlists}
    except Exception as e:
        return {"error": str(e)}


def get_playlist_tracks(playlist_id, offset=0, limit=30):
    try:
        yt = _get_ytmusic()
        if not yt:
            return {"error": "Not authenticated"}

        total_needed = offset + limit
        result = yt.get_playlist(playlist_id, limit=total_needed)

        all_tracks = result.get("tracks", [])
        page = all_tracks[offset:offset + limit]

        tracks = []
        for item in page:
            t = _extract_track(item)
            if t:
                tracks.append(t)

        has_more = len(all_tracks) > offset + limit
        return {"tracks": tracks, "has_more": has_more}
    except Exception as e:
        return {"error": str(e)}


def search(query, limit=20):
    try:
        yt = _get_ytmusic()
        if not yt:
            # Search can work without auth
            yt = YTMusic()

        results = yt.search(query, filter='songs', limit=limit)

        tracks = []
        for item in results:
            t = _extract_track(item)
            if t:
                tracks.append(t)

        return {"tracks": tracks, "has_more": False}
    except Exception as e:
        return {"error": str(e)}


# --- Playback protocol ---

def build_url(track_id):
    return "https://www.youtube.com/watch?v=" + track_id


def parse_track_id(url):
    """Extract YouTube video ID from a URL."""
    for param in url.split("?")[-1].split("&"):
        if param.startswith("v="):
            return param[2:]
    if "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    return None
