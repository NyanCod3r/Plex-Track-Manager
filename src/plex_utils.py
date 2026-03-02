"""
plex_utils.py - Plex integration and download logic for Plex-Track-Manager

Handles:
- Ensuring local files exist for a given track list (downloading via yt-dlp)
- YouTube search and yt-dlp download with FLAC/MP3 preference
- Track existence checks (filename + metadata matching)
- Plex 1-star track retrieval and deletion
- Sync statistics tracking
"""

from typing import List, Dict, Optional
from common_utils import createFolder
from plexapi.server import PlexServer
from youtubesearchpython import VideosSearch

import warnings
warnings.filterwarnings("ignore", module="eyed3.id3.frames")

import logging
import os
import subprocess
import sys
import time
import mutagen

SUPPORTED_FORMATS = [".flac", ".mp3"]
youtube_url_cache = {}


def ensure_local_files(tracks: list, playlist_name: str, music_path: str):
    """
    Ensure all tracks in the list are downloaded locally.

    File structure: MUSIC_PATH/<Playlist>/<Artist>/<Album>/<Artist - Track>.flac|mp3
    """
    if not music_path:
        logging.error("MUSIC_PATH not specified.")
        return

    logging.info(f"Ensuring local files for playlist: {playlist_name}")

    download_queue = []
    safe_playlist = sanitizeFilename(playlist_name)
    playlist_folder = os.path.join(music_path, safe_playlist)

    for track in tracks:
        track_name = track.get("title", "Unknown Track")
        artist_name = track.get("artist", "Unknown Artist")
        album_name = track.get("album", "Unknown Album")

        safe_artist = sanitizeFilename(artist_name)
        safe_album = sanitizeFilename(album_name)
        safe_track = sanitizeFilename(track_name)

        album_folder = os.path.join(playlist_folder, safe_artist, safe_album)
        createFolder(album_folder)

        prefer_flac = os.environ.get("PREFER_FLAC", "true").lower() in ["true", "1", "yes"]
        file_ext = "flac" if prefer_flac else "mp3"
        expected_filename = f"{safe_artist} - {safe_track}.{file_ext}"
        expected_filepath = os.path.join(album_folder, expected_filename)

        logging.info(f"Checking for track '{safe_track}' in path: '{album_folder}'")

        if track_exists_in_directory(album_folder, safe_track):
            continue

        if find_and_rename_track_by_tag(album_folder, artist_name, track_name, expected_filepath):
            continue

        logging.warning(f"Track not found locally. Queuing: '{safe_artist} - {safe_track}'")
        download_queue.append((album_folder, track_name, artist_name, expected_filepath))

    if download_queue:
        logging.info(f"Downloading {len(download_queue)} missing tracks...")
        download_delay = float(os.environ.get("DOWNLOAD_DELAY", "0.1"))
        for idx, (output_folder, track_name, artist_name, expected_filepath) in enumerate(download_queue, 1):
            download_track(output_folder, track_name, artist_name, expected_filepath)
            if idx < len(download_queue):
                time.sleep(download_delay)
        logging.info(f"Completed downloading {len(download_queue)} tracks")
    else:
        logging.info(f"All tracks already present for playlist: {playlist_name}")


def search_youtube_for_track(artist_name: str, track_name: str) -> Optional[str]:
    """
    Search YouTube for a track and return the URL of the top result.
    Uses an in-memory cache to avoid duplicate queries.
    """
    if not artist_name or not track_name:
        logging.error(f"Invalid input: artist_name='{artist_name}', track_name='{track_name}'")
        return None

    safe_artist = str(artist_name).strip()
    safe_track = str(track_name).strip()
    search_query = f"{safe_artist} - {safe_track}"

    if search_query in youtube_url_cache:
        cached = youtube_url_cache[search_query]
        if cached:
            logging.info(f"Found YouTube URL in cache for: '{search_query}'")
        return cached

    logging.info(f"Searching YouTube for: '{search_query}'")

    try:
        search_cmd = [sys.executable, "-m", "yt_dlp", "--get-id", "--no-playlist", f"ytsearch5:{search_query}"]
        proc = subprocess.run(search_cmd, capture_output=True, text=True, timeout=30)

        if proc.returncode == 0 and proc.stdout.strip():
            video_ids = proc.stdout.strip().split("\n")
            if video_ids and video_ids[0]:
                url = f"https://www.youtube.com/watch?v={video_ids[0]}"
                logging.info(f"Found YouTube URL via yt-dlp search: {url}")
                youtube_url_cache[search_query] = url
                return url

        logging.info("yt-dlp search failed, trying YoutubeSearchPython...")
        videos_search = VideosSearch(safe_artist + " " + safe_track, limit=5)
        search_result = videos_search.result()
        if not search_result or not isinstance(search_result, dict):
            youtube_url_cache[search_query] = None
            return None

        results = search_result.get("result", [])
        for video in results:
            if video and isinstance(video, dict) and video.get("link"):
                url = video["link"]
                logging.info(f"Using first available result: {url}")
                youtube_url_cache[search_query] = url
                return url

        logging.warning(f"No YouTube results found for '{search_query}'")
        youtube_url_cache[search_query] = None
        return None

    except subprocess.TimeoutExpired:
        logging.error(f"YouTube search timeout for '{search_query}'")
        youtube_url_cache[search_query] = None
        return None
    except TypeError as e:
        logging.error(f"Type error in YouTube library for '{search_query}': {e}")
        youtube_url_cache[search_query] = None
        return None
    except Exception as e:
        logging.error(f"General error searching YouTube for '{search_query}': {e}")
        youtube_url_cache[search_query] = None
        return None


def normalize_for_matching(text: str) -> str:
    """
    Normalize text for fuzzy matching by lowering case and removing
    common separators and punctuation.
    """
    if not text:
        return ""
    normalized = text.lower()
    for char in '/\\-_.,:;()[]\'\"':
        normalized = normalized.replace(char, "")
    return " ".join(normalized.split())


def track_exists_in_directory(folder: str, track_title: str) -> bool:
    """
    Check FLAC first, then MP3 for the track (filename + metadata match).
    """
    try:
        normalized_track = normalize_for_matching(track_title)

        for ext in (".flac", ".mp3"):
            for filename in os.listdir(folder):
                if not filename.lower().endswith(ext):
                    continue
                if " - " in filename:
                    fn_track = filename.split(" - ", 1)[1].rsplit(".", 1)[0]
                    if normalize_for_matching(fn_track) == normalized_track:
                        logging.debug(f"Found existing {ext.upper()} by filename: '{filename}'")
                        return True
                try:
                    filepath = os.path.join(folder, filename)
                    af = mutagen.File(filepath, easy=True)
                    if af:
                        tag_title = af.get("title", [None])[0]
                        if tag_title and normalize_for_matching(tag_title) == normalized_track:
                            logging.debug(f"Found existing {ext.upper()} by metadata: '{filename}'")
                            return True
                except Exception:
                    pass
    except FileNotFoundError:
        return False
    return False


def find_and_rename_track_by_tag(folder: str, artist_name: str, track_title: str, expected_filepath: str) -> bool:
    """
    Scan audio files, match by metadata, and rename if found.
    """
    try:
        normalized_artist = normalize_for_matching(artist_name)
        normalized_track = normalize_for_matching(track_title)

        for filename in os.listdir(folder):
            if not (filename.lower().endswith(".flac") or filename.lower().endswith(".mp3")):
                continue
            current = os.path.join(folder, filename)
            try:
                af = mutagen.File(current, easy=True)
                if not af:
                    continue
            except Exception:
                continue

            tag_artist = af.get("artist", [None])[0]
            tag_title = af.get("title", [None])[0]
            if tag_artist and tag_title:
                if (normalize_for_matching(tag_artist) == normalized_artist and
                        normalize_for_matching(tag_title) == normalized_track):
                    logging.info(f"Found track by metadata tag: '{filename}'")
                    if current != expected_filepath:
                        logging.warning(f"Renaming '{filename}' to '{os.path.basename(expected_filepath)}'")
                        os.rename(current, expected_filepath)
                    return True
    except FileNotFoundError:
        return False
    except Exception as e:
        logging.error(f"Error processing metadata in '{folder}': {e}")
    return False


def download_track(output_folder: str, track_name: str, artist_name: str, expected_filepath: str):
    """
    Download a single track using YouTube search + yt-dlp.
    Format is determined by PREFER_FLAC (default: true).
    """
    download_stats["downloads_attempted"] += 1
    ytdlp_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    prefer_flac = os.environ.get("PREFER_FLAC", "true").lower() in ["true", "1", "yes"]

    files_before = set()
    if os.path.exists(output_folder):
        files_before = set(os.listdir(output_folder))

    logging.info(f"Using YouTube search for '{artist_name} - {track_name}'")

    youtube_url = search_youtube_for_track(artist_name, track_name)
    if not youtube_url:
        logging.error(f"No YouTube URL found for '{artist_name} - {track_name}'")
        track_download_failure()
        return False

    try:
        output_filename = f"{sanitizeFilename(artist_name)} - {sanitizeFilename(track_name)}.%(ext)s"
        output_path = os.path.join(output_folder, output_filename)

        if prefer_flac:
            fmt = "bestaudio[ext=flac]/bestaudio[acodec*=flac]/bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best[height<=480]"
            audio_format = "flac"
        else:
            fmt = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best[height<=480]"
            audio_format = "mp3"

        cmd = _build_ytdlp_cmd(fmt, audio_format, output_path, ytdlp_log_level)
        cmd.append(youtube_url)

        logging.info(f"Downloading via yt-dlp: {youtube_url}")
        capture = ytdlp_log_level != "DEBUG"
        proc = subprocess.run(cmd, capture_output=capture, text=True, timeout=300)

        if proc.returncode == 0:
            new_audio = _check_new_audio_files(output_folder, files_before)
            if new_audio:
                for f in new_audio:
                    logging.info(f"Successfully downloaded: {f}")
                track_download_success()
                return True

        if prefer_flac:
            logging.info(f"FLAC download failed, trying MP3 fallback for '{artist_name} - {track_name}'")
            cmd_mp3 = _build_ytdlp_cmd(
                "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best[height<=480]",
                "mp3", output_path, ytdlp_log_level
            )
            cmd_mp3.append(youtube_url)
            proc_mp3 = subprocess.run(cmd_mp3, capture_output=capture, text=True, timeout=300)
            if proc_mp3.returncode == 0:
                new_audio = _check_new_audio_files(output_folder, files_before)
                if new_audio:
                    for f in new_audio:
                        logging.info(f"Downloaded MP3 fallback: {f}")
                    track_download_success()
                    return True

    except subprocess.TimeoutExpired:
        logging.error(f"yt-dlp timeout for {artist_name} - {track_name}")
    except Exception as e:
        logging.error(f"yt-dlp error: {e}")

    logging.error(f"All download methods failed for '{artist_name} - {track_name}'")
    track_download_failure()
    return False


def _build_ytdlp_cmd(fmt: str, audio_format: str, output_path: str, log_level: str) -> list:
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--format", fmt,
        "--extract-audio",
        "--audio-format", audio_format,
        "--audio-quality", "0",
        "--output", output_path,
        "--no-playlist",
        "--embed-metadata",
        "--ignore-errors",
        "--no-post-overwrites",
        "--prefer-free-formats",
    ]
    try:
        ffmpeg_result = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
        if ffmpeg_result.returncode == 0:
            cmd.extend(["--ffmpeg-location", ffmpeg_result.stdout.strip()])
    except Exception:
        pass

    if log_level == "DEBUG":
        cmd.append("--verbose")
    elif log_level in ("ERROR", "WARNING"):
        cmd.append("--quiet")
    else:
        cmd.append("--no-warnings")
    return cmd


def _check_new_audio_files(folder: str, files_before: set) -> list:
    if not os.path.exists(folder):
        return []
    files_after = set(os.listdir(folder))
    new_files = files_after - files_before
    return [f for f in new_files if f.lower().endswith(".flac") or f.lower().endswith(".mp3")]


def sanitizeFilename(name: str) -> str:
    invalid_chars = ["<", ">", ":", '"', "/", "\\", "|", "?", "*"]
    for char in invalid_chars:
        name = name.replace(char, "_")
    return name.strip()


def get_one_star_tracks(plex: PlexServer, library_name: str) -> List[Dict]:
    """
    Retrieve all tracks from a Plex library section that have a 1-star rating.
    """
    logging.info(f"Fetching 1-star rated tracks from Plex library: {library_name}...")
    one_star_tracks = []
    try:
        music_library = plex.library.section(library_name)
        for track in music_library.searchTracks():
            if hasattr(track, "userRating") and track.userRating in [1.0, 2.0]:
                one_star_tracks.append({
                    "plex_track": track,
                    "title": track.title,
                    "artist": track.artist().title if track.artist() else "Unknown",
                })
        logging.info(f"Found {len(one_star_tracks)} tracks with 1-star rating in {library_name}.")
    except Exception as e:
        logging.error(f"Error fetching 1-star tracks from library '{library_name}': {e}")
    return one_star_tracks


def delete_plex_track(track, playlist_name: str = "Unknown"):
    """
    Delete a track from the Plex library and filesystem.
    """
    track_title = track.title
    try:
        track.delete()
        logging.info(f"Deleted from Plex library: {track_title}")
        track_deletion_success()
    except Exception as e:
        logging.error(f"Failed to delete from Plex library: {track_title} - {e}")
        track_deletion_failure()


download_stats = {
    "downloads_attempted": 0,
    "downloads_successful": 0,
    "downloads_failed": 0,
    "tracks_deleted": 0,
    "delete_failures": 0,
}


def reset_stats():
    global download_stats
    download_stats = {
        "downloads_attempted": 0,
        "downloads_successful": 0,
        "downloads_failed": 0,
        "tracks_deleted": 0,
        "delete_failures": 0,
    }


def track_download_success():
    download_stats["downloads_successful"] += 1


def track_download_failure():
    download_stats["downloads_failed"] += 1


def track_deletion_success():
    download_stats["tracks_deleted"] += 1


def track_deletion_failure():
    download_stats["delete_failures"] += 1


def print_sync_recap():
    print("\n" + "=" * 60)
    print("SYNC CYCLE RECAP")
    print("=" * 60)
    print(f"Downloads Attempted: {download_stats['downloads_attempted']}")
    print(f"Downloads Successful: {download_stats['downloads_successful']}")
    print(f"Downloads Failed: {download_stats['downloads_failed']}")
    print(f"Tracks Deleted: {download_stats['tracks_deleted']}")
    print(f"Delete Failures: {download_stats['delete_failures']}")
    if download_stats["downloads_attempted"] > 0:
        rate = (download_stats["downloads_successful"] / download_stats["downloads_attempted"]) * 100
        print(f"Success Rate: {rate:.1f}%")
    print("=" * 60 + "\n")
