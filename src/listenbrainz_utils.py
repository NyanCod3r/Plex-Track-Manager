"""
listenbrainz_utils.py - ListenBrainz API integration for Plex-Track-Manager

Handles:
- Syncing Plex playlists (from JSON + live server) to ListenBrainz
- Checking LB playlists for tracks missing from Plex
- Removing 1-star tracks from all ListenBrainz playlists they appear in
"""

import json
import logging
import os
import time
from typing import Dict, List, Optional, Set, Tuple

import requests

LB_API_BASE = "https://api.listenbrainz.org"
MB_API_BASE = "https://musicbrainz.org/ws/2"
MB_USER_AGENT = "plex-track-manager/1.0 (plex-track-manager)"
MAX_TRACKS_PER_ADD = 100
MB_RATE_LIMIT = 1.0

_mb_cache: dict = {}
_mb_last_request: float = 0.0


def _lb_headers(lb_token: str) -> dict:
    return {
        "Authorization": f"Token {lb_token}",
        "Content-Type": "application/json",
    }


def _normalize(text: str) -> str:
    if not text:
        return ""
    t = text.lower()
    for ch in '/\\-_.,:;()\'"[]':
        t = t.replace(ch, "")
    return " ".join(t.split())


def _mb_search(query: str) -> str:
    """Execute a single MusicBrainz recording search and return the first MBID or empty string."""
    global _mb_last_request
    elapsed = time.time() - _mb_last_request
    if elapsed < MB_RATE_LIMIT:
        time.sleep(MB_RATE_LIMIT - elapsed)
    try:
        resp = requests.get(
            f"{MB_API_BASE}/recording/",
            params={"query": query, "fmt": "json", "limit": 5},
            headers={"User-Agent": MB_USER_AGENT},
            timeout=15,
        )
        _mb_last_request = time.time()
        if resp.status_code == 200:
            results = resp.json().get("recordings", [])
            if results:
                return results[0].get("id", "")
    except Exception:
        _mb_last_request = time.time()
    return ""


def _lookup_mbid(artist: str, title: str) -> str:
    """
    Look up a MusicBrainz recording MBID for the given artist and title.
    Tries a strict quoted search first, then a looser fallback.
    Rate-limited to 1 request/second. Results cached in memory.
    """
    cache_key = (_normalize(artist), _normalize(title))
    if cache_key in _mb_cache:
        return _mb_cache[cache_key]

    mbid = _mb_search(f'recording:"{title}" AND artist:"{artist}"')
    if not mbid:
        mbid = _mb_search(f'{title} {artist}')

    _mb_cache[cache_key] = mbid
    return mbid


def _to_jspf_track(track: dict) -> dict:
    """Convert a {title, artist} track dict to JSPF format with MBID. Returns {} if no MBID found."""
    mbid = _lookup_mbid(track.get("artist", ""), track.get("title", ""))
    if not mbid:
        return {}
    return {
        "identifier": f"https://musicbrainz.org/recording/{mbid}",
        "title": track.get("title", ""),
        "creator": track.get("artist", ""),
    }


def get_lb_playlists(lb_username: str, lb_token: str) -> List[Dict]:
    """
    Fetch all playlists for a ListenBrainz user.
    Returns a list of {title, mbid} dicts.
    """
    playlists = []
    offset = 0
    page_size = 25
    while True:
        url = f"{LB_API_BASE}/1/user/{lb_username}/playlists"
        resp = requests.get(
            url,
            headers=_lb_headers(lb_token),
            params={"count": page_size, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("playlists", [])
        for pl in batch:
            pl_data = pl.get("playlist", {})
            title = pl_data.get("title", "")
            identifier = pl_data.get("identifier", "")
            mbid = identifier.split("/")[-1] if identifier else ""
            if title and mbid:
                playlists.append({"title": title, "mbid": mbid})
        if len(batch) < page_size:
            break
        offset += page_size
    return playlists


def find_lb_playlist_mbid(lb_username: str, lb_token: str, title: str) -> Optional[str]:
    """
    Return the mbid of a ListenBrainz playlist matching the given title exactly.
    Returns None if not found.
    """
    for pl in get_lb_playlists(lb_username, lb_token):
        if pl["title"] == title:
            return pl["mbid"]
    return None


def get_lb_playlist_tracks(playlist_mbid: str, lb_token: str) -> List[Dict]:
    """
    Fetch all tracks from a ListenBrainz playlist.
    Returns a list of {title, creator, index} dicts.
    """
    url = f"{LB_API_BASE}/1/playlist/{playlist_mbid}"
    resp = requests.get(
        url,
        headers=_lb_headers(lb_token),
        params={"fetch_metadata": "false"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    raw_tracks = data.get("playlist", {}).get("track", [])
    return [
        {"title": t.get("title", ""), "creator": t.get("creator", ""), "index": idx}
        for idx, t in enumerate(raw_tracks)
    ]


def get_track_index_in_lb_playlist(
    playlist_mbid: str, lb_token: str, artist: str, title: str
) -> Optional[int]:
    """
    Find the first index of a track matching artist + title in a playlist.
    Returns None if not found.
    """
    norm_artist = _normalize(artist)
    norm_title = _normalize(title)
    for t in get_lb_playlist_tracks(playlist_mbid, lb_token):
        if _normalize(t["creator"]) == norm_artist and _normalize(t["title"]) == norm_title:
            return t["index"]
    return None


def create_lb_playlist(lb_token: str, title: str) -> Optional[str]:
    """
    Create an empty playlist on ListenBrainz.
    Returns the new playlist mbid, or None on failure.
    """
    body = {
        "playlist": {
            "title": title,
            "annotation": "Imported from Plex via Plex-Track-Manager",
            "extension": {
                "https://musicbrainz.org/doc/jspf#playlist": {"public": True}
            },
        }
    }
    resp = requests.post(
        f"{LB_API_BASE}/1/playlist/create",
        headers=_lb_headers(lb_token),
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("playlist_mbid")


def add_tracks_to_lb_playlist(playlist_mbid: str, lb_token: str, tracks: list) -> Tuple[int, int]:
    """
    Resolve MBIDs and append matched tracks to an existing ListenBrainz playlist.
    tracks: list of {title, artist} dicts.
    Returns (matched_count, skipped_count).
    """
    jspf_tracks = []
    skipped = 0
    for t in tracks:
        jspf = _to_jspf_track(t)
        if jspf:
            jspf_tracks.append(jspf)
        else:
            skipped += 1
            logging.debug(f"[LB] No MBID found for '{t.get('artist')} - {t.get('title')}', skipping.")

    if not jspf_tracks:
        return 0, skipped

    for i in range(0, len(jspf_tracks), MAX_TRACKS_PER_ADD):
        chunk = jspf_tracks[i:i + MAX_TRACKS_PER_ADD]
        body = {"playlist": {"track": chunk}}
        resp = requests.post(
            f"{LB_API_BASE}/1/playlist/{playlist_mbid}/item/add",
            headers=_lb_headers(lb_token),
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        if len(jspf_tracks) > MAX_TRACKS_PER_ADD:
            time.sleep(0.5)

    return len(jspf_tracks), skipped


def remove_track_from_lb_playlist(playlist_mbid: str, lb_token: str, track_index: int) -> bool:
    """
    Remove a single track at the given index from a ListenBrainz playlist.
    Returns True on success, raises on failure.
    """
    body = {"index": track_index, "count": 1}
    resp = requests.post(
        f"{LB_API_BASE}/1/playlist/{playlist_mbid}/item/delete",
        headers=_lb_headers(lb_token),
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    return True


def remove_track_from_all_lb_playlists(lb_token: str, lb_username: str, artist: str, title: str) -> None:
    """
    Remove a track (matched by artist+title) from every LB playlist it appears in.
    Raises on any API failure so the caller can log CRITICAL.
    """
    playlists = get_lb_playlists(lb_username, lb_token)
    for pl in playlists:
        idx = get_track_index_in_lb_playlist(pl["mbid"], lb_token, artist, title)
        if idx is not None:
            remove_track_from_lb_playlist(pl["mbid"], lb_token, idx)
            logging.info(f"[LB] Removed '{artist} - {title}' from playlist '{pl['title']}'")


def _merge_playlists(json_playlists: list, plex_playlists: list) -> list:
    merged: Dict[str, Dict[Tuple, dict]] = {}
    for source in [json_playlists, plex_playlists]:
        for pl in source:
            name = pl.get("title", "")
            if name not in merged:
                merged[name] = {}
            for item in pl.get("items", []):
                key = (_normalize(item.get("artist", "")), _normalize(item.get("title", "")))
                if key not in merged[name]:
                    merged[name][key] = item
    return [{"title": name, "items": list(tracks.values())} for name, tracks in merged.items()]


def _load_json_playlists(json_path: str) -> list:
    if not json_path or not os.path.exists(json_path):
        return []
    try:
        with open(json_path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logging.warning(f"[LB] Could not load {json_path}: {exc}")
        return []


def _load_plex_playlists(plex) -> list:
    playlists = []
    try:
        for pl in plex.playlists():
            try:
                items = pl.items()
            except Exception:
                continue
            tracks = [
                {"title": t.title, "artist": getattr(t, "grandparentTitle", None) or "Unknown Artist"}
                for t in items
                if getattr(t, "type", None) == "track"
            ]
            if tracks:
                playlists.append({"title": pl.title, "items": tracks})
    except Exception as exc:
        logging.warning(f"[LB] Could not load playlists from Plex: {exc}")
    return playlists


_LB_SYNC_EXCLUDED = {"Discover Weekly", "Release Radar"}


def sync_playlists_to_lb(plex, plex_json_path: str, lb_token: str, lb_username: str) -> dict:
    """
    Sync Plex playlists (from JSON + live Plex) to ListenBrainz.
    Creates missing playlists and adds missing tracks to existing ones.
    Playlists in _LB_SYNC_EXCLUDED are never synced.
    Returns a summary dict with created/updated/skipped/errors counts.
    """
    json_playlists = _load_json_playlists(plex_json_path)
    plex_playlists = _load_plex_playlists(plex)
    merged = _merge_playlists(json_playlists, plex_playlists)
    merged = [pl for pl in merged if pl["title"] not in _LB_SYNC_EXCLUDED]

    if not merged:
        logging.info("[LB] No playlists to sync.")
        return {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

    try:
        existing_list = get_lb_playlists(lb_username, lb_token)
        existing = {pl["title"]: pl["mbid"] for pl in existing_list}
    except Exception as exc:
        logging.error(f"[LB] Could not fetch existing LB playlists: {exc}")
        return {"created": 0, "updated": 0, "skipped": 0, "errors": 1}

    created = updated = skipped = errors = 0

    for pl in merged:
        name = pl["title"]
        tracks = pl["items"]
        try:
            if name in existing:
                mbid = existing[name]
                lb_track_set = {
                    (_normalize(t["creator"]), _normalize(t["title"]))
                    for t in get_lb_playlist_tracks(mbid, lb_token)
                }
                missing = [
                    t for t in tracks
                    if (_normalize(t.get("artist", "")), _normalize(t.get("title", ""))) not in lb_track_set
                ]
                if missing:
                    matched, skipped_tracks = add_tracks_to_lb_playlist(mbid, lb_token, missing)
                    logging.info(f"[LB] Updated '{name}': {matched} added, {skipped_tracks} skipped (no MBID)")
                    updated += 1
                else:
                    logging.debug(f"[LB] Skipped '{name}': all tracks already present")
                    skipped += 1
            else:
                mbid = create_lb_playlist(lb_token, name)
                if not mbid:
                    logging.error(f"[LB] Failed to create playlist '{name}'")
                    errors += 1
                    continue
                matched, skipped_tracks = add_tracks_to_lb_playlist(mbid, lb_token, tracks)
                logging.info(f"[LB] Created '{name}': {matched} added, {skipped_tracks} skipped (no MBID)")
                created += 1
        except Exception as exc:
            logging.error(f"[LB] Error processing playlist '{name}': {exc}")
            errors += 1

    logging.info(f"[LB] Sync done - created: {created}, updated: {updated}, skipped: {skipped}, errors: {errors}")
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}


