"""YouTube Music service adapter using YouTube Data API v3 directly."""

import os
import json as json_mod
import time

import requests as http_requests

import state

SERVICE_NAME = "youtube"
SERVICE_DISPLAY_NAME = "YouTube"

# OAuth credentials loaded from config file (never hardcoded)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OAUTH_CONFIG_FILE = os.path.join(_BASE_DIR, "oauth_config.json")
OAUTH_FILE = os.path.join(_BASE_DIR, "oauth.json")
OAUTH_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YT_API_BASE = "https://www.googleapis.com/youtube/v3"


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


# --- Internal helpers ---

def _save_oauth(token_data):
    """Save OAuth token data with restrictive permissions."""
    fd = os.open(OAUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json_mod.dump(token_data, f, indent=2)


def _get_access_token():
    """Get a valid access token, refreshing if expired."""
    if not _client_id:
        return None
    if not os.path.exists(OAUTH_FILE):
        return None
    try:
        with open(OAUTH_FILE) as f:
            token_data = json_mod.load(f)
        if token_data.get("expires_at", 0) < time.time() + 60:
            resp = http_requests.post("https://oauth2.googleapis.com/token", data={
                "client_id": _client_id,
                "client_secret": _client_secret,
                "refresh_token": token_data["refresh_token"],
                "grant_type": "refresh_token",
            }, timeout=10)
            if resp.status_code == 200:
                new_data = resp.json()
                token_data["access_token"] = new_data["access_token"]
                token_data["expires_at"] = time.time() + new_data.get("expires_in", 3600)
                token_data["expires_in"] = new_data.get("expires_in", 3600)
                _save_oauth(token_data)
                print("[AUTH] Token refreshed", flush=True)
            else:
                print("[AUTH] Token refresh failed: {}".format(resp.text), flush=True)
                return None
        return token_data["access_token"]
    except Exception as e:
        print("[AUTH] Error getting access token: {}".format(e), flush=True)
        return None


def _api_get(endpoint, params=None):
    """Make an authenticated GET request to YouTube Data API v3."""
    token = _get_access_token()
    if not token:
        return None
    headers = {"Authorization": "Bearer {}".format(token)}
    url = "{}/{}".format(YT_API_BASE, endpoint)
    resp = http_requests.get(url, headers=headers, params=params or {}, timeout=15)
    if resp.status_code == 200:
        return resp.json()
    print("[API] {} error: {}".format(endpoint, resp.text[:200]), flush=True)
    return None


# --- Auth protocol ---

def is_authenticated():
    return _client_id is not None and os.path.exists(OAUTH_FILE) and _get_access_token() is not None


def auth_status():
    if not _client_id:
        return {"authenticated": False, "error": "OAuth not configured. See README for setup instructions."}
    return {"authenticated": is_authenticated()}


def auth_start():
    if not _client_id:
        return {"error": "OAuth not configured. Place oauth_config.json in the app directory. See README for instructions."}
    try:
        resp = http_requests.post("https://oauth2.googleapis.com/device/code", data={
            "client_id": _client_id,
            "scope": OAUTH_SCOPE,
        }, timeout=10)
        if resp.status_code != 200:
            return {"error": "Failed to start auth: {}".format(resp.text)}
        code = resp.json()
        return {
            "url": code["verification_url"],
            "user_code": code["user_code"],
            "device_code": code["device_code"],
        }
    except Exception as e:
        return {"error": str(e)}


def auth_complete():
    if not _client_id:
        return {"error": "OAuth not configured."}
    if not state.auth_pending:
        return {"error": "No auth flow in progress. Start auth first."}
    try:
        resp = http_requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": _client_id,
            "client_secret": _client_secret,
            "device_code": state.auth_pending["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }, timeout=10)
        if resp.status_code != 200:
            error_data = resp.json()
            error_type = error_data.get("error", "")
            if error_type == "authorization_pending":
                return {"error": "Still waiting for authorization. Please complete sign-in on your device."}
            if error_type == "slow_down":
                return {"error": "Please wait a moment before trying again."}
            return {"error": "Auth failed: {}".format(error_data.get("error_description", resp.text))}
        token_data = resp.json()
        token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
        _save_oauth(token_data)
        print("[AUTH] OAuth token saved successfully", flush=True)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


# --- Library protocol ---

def get_liked(offset=0, limit=20):
    try:
        params = {
            "part": "snippet",
            "playlistId": "LM",
            "maxResults": min(limit, 50),
        }
        if offset > 0:
            page_token = None
            skipped = 0
            while skipped < offset:
                p = {"part": "snippet", "playlistId": "LM", "maxResults": 50}
                if page_token:
                    p["pageToken"] = page_token
                d = _api_get("playlistItems", p)
                if not d:
                    break
                page_token = d.get("nextPageToken")
                skipped += len(d.get("items", []))
                if not page_token:
                    break
            if page_token:
                params["pageToken"] = page_token
        data = _api_get("playlistItems", params)
        if not data:
            return {"error": "Failed to fetch liked songs. Please try signing in again."}
        tracks = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            vid_id = snippet.get("resourceId", {}).get("videoId", "")
            title = snippet.get("title", "Unknown")
            channel = snippet.get("videoOwnerChannelTitle", "")
            if channel:
                channel = channel.replace(" - Topic", "")
                title = "{} - {}".format(channel, title)
            thumb = snippet.get("thumbnails", {}).get("medium", {}).get("url", "")
            if not thumb and vid_id:
                thumb = "https://i.ytimg.com/vi/{}/mqdefault.jpg".format(vid_id)
            if vid_id:
                tracks.append({"id": vid_id, "title": title, "thumbnail": thumb})
        has_more = data.get("nextPageToken") is not None
        return {"tracks": tracks, "has_more": has_more}
    except Exception as e:
        return {"error": str(e)}


def get_playlists():
    try:
        data = _api_get("playlists", {
            "part": "snippet,contentDetails",
            "mine": "true",
            "maxResults": 50,
        })
        if not data:
            return {"error": "Failed to fetch playlists. Please try signing in again."}
        playlists = []
        for item in data.get("items", []):
            pl_id = item.get("id", "")
            snippet = item.get("snippet", {})
            title = snippet.get("title", "Unknown")
            thumb = snippet.get("thumbnails", {}).get("medium", {}).get("url", "")
            count = item.get("contentDetails", {}).get("itemCount", 0)
            if pl_id:
                playlists.append({"id": pl_id, "title": title, "thumbnail": thumb, "count": count})
        return {"playlists": playlists}
    except Exception as e:
        return {"error": str(e)}


def get_playlist_tracks(playlist_id, offset=0, limit=30):
    try:
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": min(limit, 50),
        }
        if offset > 0:
            page_token = None
            skipped = 0
            while skipped < offset:
                p = {"part": "snippet", "playlistId": playlist_id, "maxResults": 50}
                if page_token:
                    p["pageToken"] = page_token
                d = _api_get("playlistItems", p)
                if not d:
                    break
                page_token = d.get("nextPageToken")
                skipped += len(d.get("items", []))
                if not page_token:
                    break
            if page_token:
                params["pageToken"] = page_token
        data = _api_get("playlistItems", params)
        if not data:
            return {"error": "Failed to fetch playlist tracks."}
        tracks = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            vid_id = snippet.get("resourceId", {}).get("videoId", "")
            title = snippet.get("title", "Unknown")
            channel = snippet.get("videoOwnerChannelTitle", "")
            if channel:
                channel = channel.replace(" - Topic", "")
                title = "{} - {}".format(channel, title)
            thumb = snippet.get("thumbnails", {}).get("medium", {}).get("url", "")
            if not thumb and vid_id:
                thumb = "https://i.ytimg.com/vi/{}/mqdefault.jpg".format(vid_id)
            if vid_id:
                tracks.append({"id": vid_id, "title": title, "thumbnail": thumb})
        has_more = data.get("nextPageToken") is not None
        return {"tracks": tracks, "has_more": has_more}
    except Exception as e:
        return {"error": str(e)}


def search(query, limit=20):
    """Search using ytmusicapi (unauthenticated, no API quota cost)."""
    try:
        from ytmusicapi import YTMusic
        yt = YTMusic()
        results = yt.search(query, filter="songs", limit=limit)
        tracks = []
        for item in results:
            vid_id = item.get("videoId", "")
            if not vid_id:
                continue
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
            tracks.append({"id": vid_id, "title": title, "thumbnail": thumb})
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
