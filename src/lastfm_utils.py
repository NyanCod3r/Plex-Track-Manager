"""
lastfm_utils.py - Last.fm API integration for Plex-Track-Manager

Syncs Plex music data (loved tracks, play history) to Last.fm and generates
two recommendation playlists:
- Discover Weekly: Tracks from similar artists the user hasn't listened to
- Release Radar: New releases from the user's favorite artists

Key functions:
- get_lastfm_network: Connect to Last.fm with full authentication
- sync_plex_to_lastfm: Push loved tracks and scrobbles from Plex to Last.fm
- generate_discover_weekly: Build a playlist of recommended tracks
- generate_release_radar: Build a playlist of new releases from loved artists
"""

import logging
import json
import os
import time
from datetime import datetime, timedelta

import pylast
import musicbrainzngs

musicbrainzngs.set_useragent("Plex-Track-Manager", "0.3.0", "https://github.com/NyanCod3r/Plex-Track-Manager")
logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
logging.getLogger("pylast").setLevel(logging.WARNING)

SYNC_STATE_FILE = os.environ.get("SYNC_STATE_FILE", "lastfm_sync_state.json")


def get_lastfm_network(api_key, api_secret, username, password):
    """
    Connect to Last.fm with full authentication.
    Returns a pylast.LastFMNetwork instance or None on failure.
    """
    try:
        password_hash = pylast.md5(password)
        network = pylast.LastFMNetwork(
            api_key=api_key,
            api_secret=api_secret,
            username=username,
            password_hash=password_hash,
        )
        network.get_user(username)
        return network
    except Exception as e:
        logging.error(f"\U0000274C [LASTFM] Failed to connect to Last.fm: {e}")
        return None


def _load_sync_state():
    if os.path.exists(SYNC_STATE_FILE):
        try:
            with open(SYNC_STATE_FILE, "r") as fh:
                return json.load(fh)
        except Exception:
            pass
    sync_full_history = os.environ.get("SYNC_FULL_HISTORY", "true").lower() in ["true", "1", "yes"]
    default_ts = 0 if sync_full_history else int(time.time())
    return {"last_scrobble_timestamp": default_ts, "loved_hashes": [], "recommendation_history": {}}


def _save_sync_state(state):
    state_dir = os.path.dirname(SYNC_STATE_FILE)
    if state_dir:
        os.makedirs(state_dir, exist_ok=True)
    with open(SYNC_STATE_FILE, "w") as fh:
        json.dump(state, fh, indent=2)


def _track_hash(artist: str, title: str) -> str:
    return f"{artist}:{title}".lower().strip()


def _get_recommendation_history(state: dict) -> dict:
    return state.get("recommendation_history", {})


def _record_recommended_tracks(state: dict, tracks: list):
    history = state.get("recommendation_history", {})
    now = int(time.time())
    for track in tracks:
        h = _track_hash(track.get("artist", ""), track.get("title", ""))
        history[h] = now
    state["recommendation_history"] = history


def _filter_already_recommended(tracks: list, state: dict, playlist_label: str) -> list:
    cooldown_days = int(os.environ.get("RECOMMENDATION_COOLDOWN_DAYS", "") or 90)
    cooldown_seconds = cooldown_days * 86400
    now = int(time.time())
    history = _get_recommendation_history(state)
    filtered = []
    skipped = 0
    for track in tracks:
        h = _track_hash(track.get("artist", ""), track.get("title", ""))
        last_recommended = history.get(h)
        if last_recommended and (now - last_recommended) < cooldown_seconds:
            skipped += 1
            continue
        filtered.append(track)
    if skipped:
        logging.debug(f"\U0001F504 [{playlist_label}] Skipped {skipped} recently recommended tracks (cooldown: {cooldown_days}d)")
    return filtered


def sync_plex_to_lastfm(plex, network):
    """
    Push loved tracks (4-5 star ratings) and recent play history from all
    Plex music libraries to Last.fm.
    """
    state = _load_sync_state()

    music_sections = [s for s in plex.library.sections() if s.type == "artist"]
    if not music_sections:
        logging.warning("\U000026A0\uFE0F  [SYNC] No music libraries found in Plex")
        return

    loved_hashes = set(state.get("loved_hashes", []))
    loved_count = 0
    for section in music_sections:
        try:
            tracks = section.searchTracks()
            for track in tracks:
                if not (hasattr(track, "userRating") and track.userRating and track.userRating >= 8.0):
                    continue
                artist_title = track.artist().title if track.artist() else "Unknown"
                track_hash = f"{artist_title}:{track.title}".lower()
                if track_hash in loved_hashes:
                    continue
                try:
                    lastfm_track = network.get_track(artist_title, track.title)
                    lastfm_track.love()
                    loved_hashes.add(track_hash)
                    loved_count += 1
                    logging.debug(f"\U00002764\uFE0F  [SYNC] Loved on Last.fm: {artist_title} - {track.title}")
                except Exception as e:
                    logging.debug(f"\U0000274C [SYNC] Could not love track: {e}")
        except Exception as e:
            logging.warning(f"\U000026A0\uFE0F  [SYNC] Error reading library '{section.title}': {e}")

    state["loved_hashes"] = list(loved_hashes)

    if loved_count:
        logging.debug(f"\U00002764\uFE0F  [SYNC] Loved {loved_count} tracks on Last.fm")
    else:
        logging.debug("\U00002764\uFE0F  [SYNC] No new loved tracks to sync")

    scrobble_count = 0
    scrobble_errors = 0
    last_ts = state.get("last_scrobble_timestamp", int(time.time()))
    min_date = datetime.fromtimestamp(last_ts + 1)
    logging.info(f"\U0001F504 [SCROBBLE] Querying play history since {min_date} (ts={last_ts})")
    total_history = 0
    for section in music_sections:
        try:
            history = section.history(mindate=min_date)
            total_history += len(history)
            if history:
                logging.info(f"\U0001F504 [SCROBBLE] Library '{section.title}': {len(history)} plays to scrobble")
            for item in history:
                try:
                    ts = int(item.viewedAt.timestamp()) if hasattr(item, "viewedAt") and item.viewedAt else int(time.time())
                    artist_name = item.grandparentTitle if hasattr(item, "grandparentTitle") else "Unknown"
                    album_name = item.parentTitle if hasattr(item, "parentTitle") else ""
                    network.scrobble(artist=artist_name, title=item.title, timestamp=ts, album=album_name)
                    scrobble_count += 1
                    state["last_scrobble_timestamp"] = max(state.get("last_scrobble_timestamp", 0), ts)
                except Exception as e:
                    scrobble_errors += 1
                    logging.warning(f"\U0000274C [SCROBBLE] Failed: {artist_name} - {item.title}: {e}")
        except Exception as e:
            logging.error(f"\U0000274C [SCROBBLE] Error reading history for '{section.title}': {e}")

    logging.info(f"\U0001F504 [SYNC] Done - loved {loved_count}, scrobbled {scrobble_count}/{total_history} tracks"
                 + (f", {scrobble_errors} errors" if scrobble_errors else ""))

    _save_sync_state(state)


def generate_discover_weekly(network, max_tracks=20):
    """
    Build a 'Discover Weekly' track list using Last.fm similar-artist
    recommendations.

    1. Fetch the user's top artists (last 3 months).
    2. For each top artist get similar artists the user doesn't know.
    3. Pick top tracks from those artists.
    """
    user = network.get_user(network.username)

    try:
        top_artists = user.get_top_artists(period=pylast.PERIOD_3MONTHS, limit=30)
    except Exception as e:
        logging.error(f"\U0000274C [DISCOVER WEEKLY] Failed to get top artists from Last.fm: {e}")
        return []

    known_artists = {item.item.name.lower() for item in top_artists}
    logging.debug(f"\U0001F3B5 [DISCOVER WEEKLY] User has {len(known_artists)} known artists (last 3 months)")

    similar_artists = set()
    for item in top_artists[:15]:
        try:
            logging.debug(f"\U0001F3B5 [DISCOVER WEEKLY] Finding artists similar to '{item.item.name}'...")
            for similar in item.item.get_similar(limit=5):
                name = similar.item.name
                if name.lower() not in known_artists:
                    similar_artists.add(name)
        except Exception as e:
            logging.debug(f"\U0000274C [DISCOVER WEEKLY] Could not get similar artists for {item.item.name}: {e}")
        time.sleep(0.25)

    logging.debug(f"\U0001F3B5 [DISCOVER WEEKLY] Found {len(similar_artists)} new similar artists")

    tracks = []
    for artist_name in list(similar_artists)[:30]:
        if len(tracks) >= max_tracks:
            break
        try:
            logging.debug(f"\U0001F3B5 [DISCOVER WEEKLY] Fetching top tracks for '{artist_name}'...")
            artist = network.get_artist(artist_name)
            for track_item in artist.get_top_tracks(limit=3):
                tracks.append({
                    "title": track_item.item.title,
                    "artist": artist_name,
                    "album": "Unknown Album",
                })
                if len(tracks) >= max_tracks:
                    break
        except Exception as e:
            logging.debug(f"\U0000274C [DISCOVER WEEKLY] Could not get tracks for {artist_name}: {e}")
        time.sleep(0.25)

    logging.debug(f"\U0001F3B5 [DISCOVER WEEKLY] Generated playlist with {len(tracks)} candidates")

    state = _load_sync_state()
    filtered = _filter_already_recommended(tracks[:max_tracks], state, "DISCOVER WEEKLY")
    _record_recommended_tracks(state, filtered)
    _save_sync_state(state)

    logging.info(f"\U0001F3B5 [DISCOVER WEEKLY] Final playlist: {len(filtered)} tracks")
    return filtered


def generate_release_radar(network, max_tracks=20, days_back=30):
    """
    Build a 'Release Radar' track list by checking MusicBrainz for recent
    releases from the user's favourite artists.

    1. Fetch top and loved artists from Last.fm.
    2. For each artist, query MusicBrainz for release groups in the last
       *days_back* days.
    3. Collect tracks from those releases.
    """
    user = network.get_user(network.username)

    try:
        top_artists = user.get_top_artists(period=pylast.PERIOD_6MONTHS, limit=50)
    except Exception as e:
        logging.error(f"\U0000274C [RELEASE RADAR] Failed to get top artists from Last.fm: {e}")
        return []

    artist_names = [item.item.name for item in top_artists]

    try:
        for item in user.get_loved_tracks(limit=200):
            name = item.track.artist.name
            if name not in artist_names:
                artist_names.append(name)
    except Exception:
        pass

    logging.debug(f"\U0001F4E1 [RELEASE RADAR] Checking {len(artist_names)} artists for new releases")

    cutoff = datetime.now() - timedelta(days=days_back)
    tracks = []

    for artist_name in artist_names:
        if len(tracks) >= max_tracks:
            break
        try:
            result = musicbrainzngs.search_artists(artist=artist_name, limit=1)
            artist_list = result.get("artist-list", [])
            if not artist_list:
                continue
            artist_id = artist_list[0]["id"]

            releases = musicbrainzngs.browse_release_groups(
                artist=artist_id,
                release_type=["album", "single", "ep"],
                limit=10,
            )

            for rg in releases.get("release-group-list", []):
                first_release = rg.get("first-release-date", "")
                if not first_release:
                    continue
                try:
                    if len(first_release) == 4:
                        rd = datetime(int(first_release), 1, 1)
                    elif len(first_release) == 7:
                        rd = datetime(int(first_release[:4]), int(first_release[5:7]), 1)
                    else:
                        rd = datetime.strptime(first_release[:10], "%Y-%m-%d")
                    if rd < cutoff:
                        continue
                except Exception:
                    continue

                try:
                    rel_list = musicbrainzngs.browse_releases(
                        release_group=rg["id"],
                        includes=["recordings"],
                        limit=1,
                    )
                    for release in rel_list.get("release-list", []):
                        for medium in release.get("medium-list", []):
                            for rec in medium.get("track-list", []):
                                title = rec.get("recording", {}).get("title", "")
                                if title:
                                    tracks.append({
                                        "title": title,
                                        "artist": artist_name,
                                        "album": rg.get("title", "Unknown Album"),
                                    })
                                    if len(tracks) >= max_tracks:
                                        break
                            if len(tracks) >= max_tracks:
                                break
                except Exception as e:
                    logging.debug(f"\U0000274C [RELEASE RADAR] Could not get release tracks: {e}")

                time.sleep(1)  # MusicBrainz rate limit
                if len(tracks) >= max_tracks:
                    break

            time.sleep(1)
        except Exception as e:
            logging.debug(f"\U0000274C [RELEASE RADAR] Could not check releases for {artist_name}: {e}")
            time.sleep(1)

    logging.debug(f"\U0001F4E1 [RELEASE RADAR] Generated playlist with {len(tracks)} candidates")

    state = _load_sync_state()
    filtered = _filter_already_recommended(tracks[:max_tracks], state, "RELEASE RADAR")
    _record_recommended_tracks(state, filtered)
    _save_sync_state(state)

    logging.info(f"\U0001F4E1 [RELEASE RADAR] Final playlist: {len(filtered)} tracks")
    return filtered
