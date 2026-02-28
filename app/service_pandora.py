"""Pandora service adapter (stub)."""

SERVICE_NAME = "pandora"
SERVICE_DISPLAY_NAME = "Pandora"


def is_authenticated():
    return False


def auth_status():
    return {"authenticated": False}


def auth_start():
    return {"error": "Pandora not yet implemented"}


def auth_complete():
    return {"error": "Pandora not yet implemented"}


def get_liked(offset=0, limit=20):
    return {"tracks": [], "has_more": False}


def get_playlists():
    return {"playlists": []}


def get_playlist_tracks(playlist_id, offset=0, limit=20):
    return {"tracks": [], "has_more": False}


def search(query, limit=20):
    return {"tracks": [], "has_more": False}


def build_url(track_id):
    return "https://www.pandora.com/track/" + track_id


def parse_track_id(url):
    if "/track/" in url:
        return url.split("/track/")[-1].split("?")[0]
    return None
