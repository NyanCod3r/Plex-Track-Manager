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

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s",
    level=log_level,
)

logging.info("Starting Plex-Track-Manager...")


def main():
    plex_url = os.environ.get("PLEX_URL")
    plex_token = os.environ.get("PLEX_TOKEN")
    music_path = os.environ.get("MUSIC_PATH", "/music")

    if not plex_url or not plex_token:
        logging.error("PLEX_URL and PLEX_TOKEN must be set. Exiting.")
        return

    plex = PlexServer(plex_url, plex_token)
    logging.info("Connected to Plex.")

    lastfm_api_key = os.environ.get("LASTFM_API_KEY")
    lastfm_api_secret = os.environ.get("LASTFM_API_SECRET")
    lastfm_username = os.environ.get("LASTFM_USERNAME")
    lastfm_password = os.environ.get("LASTFM_PASSWORD")

    if not all([lastfm_api_key, lastfm_api_secret, lastfm_username, lastfm_password]):
        logging.error(
            "Last.fm credentials not set. "
            "Need LASTFM_API_KEY, LASTFM_API_SECRET, LASTFM_USERNAME, LASTFM_PASSWORD. Exiting."
        )
        return

    network = get_lastfm_network(lastfm_api_key, lastfm_api_secret, lastfm_username, lastfm_password)
    if not network:
        logging.error("Failed to connect to Last.fm. Exiting.")
        return

    logging.info("Connected to Last.fm.")

    seconds_to_wait = int(os.environ.get("SECONDS_TO_WAIT", "") or 3600)
    max_discover_tracks = int(os.environ.get("MAX_DISCOVER_TRACKS", "") or 20)
    max_radar_tracks = int(os.environ.get("MAX_RADAR_TRACKS", "") or 20)
    radar_days_back = int(os.environ.get("RADAR_DAYS_BACK", "") or 30)

    while True:
        try:
            reset_stats()

            logging.info("Syncing Plex data to Last.fm...")
            sync_plex_to_lastfm(plex, network)

            logging.info("Generating Discover Weekly...")
            discover_tracks = generate_discover_weekly(network, max_tracks=max_discover_tracks)
            if discover_tracks:
                ensure_local_files(discover_tracks, "Discover Weekly", music_path)

            logging.info("Generating Release Radar...")
            radar_tracks = generate_release_radar(network, max_tracks=max_radar_tracks, days_back=radar_days_back)
            if radar_tracks:
                ensure_local_files(radar_tracks, "Release Radar", music_path)

            process_one_star_deletions(plex)

            print_sync_recap()

            logging.info(f"Waiting {seconds_to_wait} seconds before next sync...")
            time.sleep(seconds_to_wait)
        except KeyboardInterrupt:
            logging.info("Shutting down Plex-Track-Manager.")
            break
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            time.sleep(60)


def process_one_star_deletions(plex):
    """
    Scan all Plex music libraries for 1-star rated tracks and delete them
    from the Plex library and the filesystem.
    """
    logging.info("Checking for 1-star rated tracks...")

    music_sections = [s for s in plex.library.sections() if s.type == "artist"]
    total_deleted = 0

    for section in music_sections:
        one_star = get_one_star_tracks(plex, section.title)
        if not one_star:
            continue

        logging.info(f"Found {len(one_star)} 1-star tracks in '{section.title}'")

        for track_info in one_star:
            try:
                delete_plex_track(track_info["plex_track"], section.title)
                total_deleted += 1
            except Exception as e:
                logging.error(f"Failed to delete: {e}")

    if total_deleted:
        logging.info(f"Deleted {total_deleted} 1-star tracks")


if __name__ == "__main__":
    main()
