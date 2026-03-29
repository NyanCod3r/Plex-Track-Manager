"""
main.py - Entry point for Plex-Track-Manager

Generates Discover Weekly and Release Radar playlists using Last.fm
recommendations based on your Plex listening history, then downloads
tracks via yt-dlp.
"""

import os
import logging
import time

from plexapi.server import PlexServer
from requests.exceptions import ConnectionError, ConnectTimeout

from lastfm_utils import (
    get_lastfm_network,
    sync_plex_to_lastfm,
    generate_discover_weekly,
    generate_release_radar,
)
from plex_utils import (
    get_one_star_tracks,
    delete_plex_track,
    reset_stats,
    print_sync_recap,
    ensure_local_files,
)

VERSION = "0.3.3" # x-release-please-version

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s",
    level=log_level,
)

BANNER = f"""
 ____  _            _____             _
|  _ \\| | _____  __/_   _| __ __ _ __| | __
| |_) | |/ _ \\ \\/ /  | || '__/ _` / __| |/ /
|  __/| |  __/>  <   | || | | (_| \\__ \\   <
|_|   |_|\\___/_/\\_\\  |_||_|  \\__,_|___/_|\\_\\
  __  __
 |  \\/  | __ _ _ __   __ _  __ _  ___ _ __
 | |\\/| |/ _` | '_ \\ / _` |/ _` |/ _ \\ '__|
 | |  | | (_| | | | | (_| | (_| |  __/ |
 |_|  |_|\\__,_|_| |_|\\__,_|\\__, |\\___|_|
                            |___/
                                    v{{version}}
"""

release_version = os.environ.get("RELEASE_VERSION", "").lstrip("v") or VERSION
BANNER = BANNER.replace("{{version}}", release_version)

print(BANNER)
logging.info(f"Starting Plex-Track-Manager v{release_version}...")


def connect_plex(plex_url, plex_token, retries=5, delay=10):
    for attempt in range(1, retries + 1):
        try:
            plex = PlexServer(plex_url, plex_token)
            logging.info("[PLEX] Connected to Plex server.")
            return plex
        except (ConnectionError, ConnectTimeout) as e:
            if attempt < retries:
                logging.warning(f"[PLEX] Connection attempt {attempt}/{retries} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logging.error(f"[PLEX] Failed to connect after {retries} attempts: {e}")
                return None


def main():
    plex_url = os.environ.get("PLEX_URL")
    plex_token = os.environ.get("PLEX_TOKEN")
    music_path = os.environ.get("MUSIC_PATH", "/music")

    if not plex_url or not plex_token:
        logging.error("[PLEX] PLEX_URL and PLEX_TOKEN must be set. Exiting.")
        return

    plex = connect_plex(plex_url, plex_token)
    if not plex:
        return

    lastfm_api_key = os.environ.get("LASTFM_API_KEY")
    lastfm_api_secret = os.environ.get("LASTFM_API_SECRET")
    lastfm_username = os.environ.get("LASTFM_USERNAME")
    lastfm_password = os.environ.get("LASTFM_PASSWORD")

    if not all([lastfm_api_key, lastfm_api_secret, lastfm_username, lastfm_password]):
        logging.error(
            "[LASTFM] Last.fm credentials not set. "
            "Need LASTFM_API_KEY, LASTFM_API_SECRET, LASTFM_USERNAME, LASTFM_PASSWORD. Exiting."
        )
        return

    network = get_lastfm_network(lastfm_api_key, lastfm_api_secret, lastfm_username, lastfm_password)
    if not network:
        logging.error("[LASTFM] Failed to connect to Last.fm. Exiting.")
        return

    logging.info("[LASTFM] Connected to Last.fm.")

    seconds_to_wait = int(os.environ.get("SECONDS_TO_WAIT", "") or 3600)
    max_discover_tracks = int(os.environ.get("MAX_DISCOVER_TRACKS", "") or 20)
    max_radar_tracks = int(os.environ.get("MAX_RADAR_TRACKS", "") or 20)
    radar_days_back = int(os.environ.get("RADAR_DAYS_BACK", "") or 30)

    while True:
        try:
            reset_stats()

            logging.info("\U0001F504 [SYNC] Syncing Plex to Last.fm...")
            sync_plex_to_lastfm(plex, network)

            logging.info("\U0001F3B5 [DISCOVER WEEKLY] Generating playlist...")
            discover_tracks = generate_discover_weekly(network, max_tracks=max_discover_tracks)
            if discover_tracks:
                ensure_local_files(discover_tracks, "Discover Weekly", music_path)
            else:
                logging.info("\U0001F3B5 [DISCOVER WEEKLY] No new tracks to recommend")

            logging.info("\U0001F4E1 [RELEASE RADAR] Generating playlist...")
            radar_tracks = generate_release_radar(network, max_tracks=max_radar_tracks, days_back=radar_days_back)
            if radar_tracks:
                ensure_local_files(radar_tracks, "Release Radar", music_path)
            else:
                logging.info("\U0001F4E1 [RELEASE RADAR] No new releases found")

            process_one_star_deletions(plex)

            print_sync_recap()

            logging.info(f"\U000023F3 [SLEEP] Waiting {seconds_to_wait}s before next sync cycle...")
            time.sleep(seconds_to_wait)
        except KeyboardInterrupt:
            logging.info("\U0001F44B [SHUTDOWN] Plex-Track-Manager stopped by user.")
            break
        except Exception as e:
            logging.error(f"\U0001F4A5 [ERROR] Unexpected error in main loop: {e}")
            time.sleep(60)


def process_one_star_deletions(plex):
    """
    Scan all Plex music libraries for 1-star rated tracks and delete them
    from the Plex library and the filesystem.
    """
    logging.info("\U0001F5D1\uFE0F  [CLEANUP] Scanning for 1-star rated tracks...")

    music_sections = [s for s in plex.library.sections() if s.type == "artist"]
    total_deleted = 0

    for section in music_sections:
        one_star = get_one_star_tracks(plex, section.title)
        if not one_star:
            continue

        logging.debug(f"\U0001F5D1\uFE0F  [CLEANUP] Found {len(one_star)} 1-star tracks in library '{section.title}'")

        for track_info in one_star:
            try:
                delete_plex_track(track_info["plex_track"], section.title)
                total_deleted += 1
            except Exception as e:
                logging.error(f"\U0001F5D1\uFE0F  [CLEANUP] Failed to delete: {e}")

    if total_deleted:
        logging.info(f"\U0001F5D1\uFE0F  [CLEANUP] Done - deleted {total_deleted} tracks")
    else:
        logging.info(f"\U0001F5D1\uFE0F  [CLEANUP] Done - scanned {len(music_sections)} libraries, no 1-star tracks found")


if __name__ == "__main__":
    main()
