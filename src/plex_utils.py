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

import difflib
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import mutagen

SUPPORTED_FORMATS = [".flac", ".mp3"]
youtube_url_cache = {}


# Words/phrases that yt-dlp's --embed-metadata injects from YouTube titles and
# uploader names (e.g. "Official Video", "VEVO", "RHINO"). These are stripped
# from title/artist/album before tagging.
STRIP_WORDS = [
    "official music video",
    "official lyric video",
    "official audio video",
    "official hd video",
    "official teaser video",
    "official trailer video",
    "official video",
    "official audio",
    "lyric video",
    "music video",
    "vevo",
    "rhino",
]

# Album placeholders that mean "no real album". These are written as "Single"
# (so the folder becomes Artist/Single/...).
SINGLE_ALIASES = {
    "standalone recordings",
    "standalone recording",
    "non-album tracks",
    "non-album track",
    "unknown album",
    "unknownalbum",
}

# YouTube-specific tags (video description / URL) that are cleared after download.
YOUTUBE_JUNK_TAGS = ("comment", "description", "synopsis", "purl")

# Minimum title-match score (0..1) required to accept a YouTube search result.
YOUTUBE_MIN_SCORE = 0.7

# Allowed difference (seconds) between expected and actual audio duration before
# a download is considered the wrong video.
DURATION_TOLERANCE = 25.0


def strip_words(text: str) -> str:
    """Remove YouTube junk words/phrases from a name and clean up leftovers."""
    if not text:
        return text
    text = str(text)
    for word in sorted(STRIP_WORDS, key=len, reverse=True):
        text = re.sub(re.escape(word), "", text, flags=re.IGNORECASE)
    text = re.sub(r"[\(\[]\s*[\)\]]", "", text)
    text = re.sub(r"\s*-\s*$", "", text)
    text = re.sub(r"^\s*-\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_album(album: str) -> str:
    """Return 'Single' when the album is missing or a known placeholder."""
    if not album:
        return "Single"
    key = str(album).strip().strip("[]").strip().lower()
    if key in SINGLE_ALIASES:
        return "Single"
    return str(album).strip()


_COMMON_WORDS = {
    "the", "a", "an", "and", "of", "in", "on", "at", "to", "for",
    "is", "are", "it", "with", "feat", "ft", "vs",
}


def _significant_words(text: str) -> set:
    """Lowercase word tokens after stripping junk, minus common filler words."""
    words = set(re.findall(r"[a-z0-9]+", strip_words(text or "").lower()))
    return words - _COMMON_WORDS


def _metadata_mismatch(old_artist: str, old_title: str, new_artist: str, new_title: str) -> bool:
    """
    True when the embedded artist/title share no meaningful words with the
    requested track - a strong signal that the wrong video was downloaded.
    """
    old_a = _significant_words(old_artist)
    old_t = _significant_words(old_title)
    new_a = _significant_words(new_artist)
    new_t = _significant_words(new_title)
    if not old_a and not old_t:
        return False  # nothing embedded to compare against
    return not (old_a & new_a) and not (old_t & new_t)


def _youtube_title_score(title: str, artist_name: str, track_name: str) -> float:
    """Score (0..1) how well a YouTube title matches the requested artist/track."""
    t = normalize_for_matching(title)
    a = normalize_for_matching(artist_name)
    tr = normalize_for_matching(track_name)
    if not tr:
        return 0.0
    score = 0.7 if (tr and tr in t) else 0.35 * difflib.SequenceMatcher(None, tr, t).ratio()
    if a:
        score += 0.3 if a in t else 0.15 * difflib.SequenceMatcher(None, a, t).ratio()
    return score


def _audio_duration(filepath: str):
    try:
        info = mutagen.File(filepath).info
        return getattr(info, "length", None)
    except Exception:
        return None


def _read_embedded_artist_title(filepath: str):
    try:
        audio = mutagen.File(filepath, easy=True)
        if audio is None:
            return "", ""
        return (audio.get("artist") or [""])[0], (audio.get("title") or [""])[0]
    except Exception:
        return "", ""


def _download_is_valid(filepath: str, artist_name: str, track_name: str, expected_duration) -> tuple:
    """
    Return (ok, reason). ok=False means the downloaded file looks like the
    wrong video/audio and should be quarantined instead of tagged.
    """
    if expected_duration:
        actual = _audio_duration(filepath)
        if actual is not None and abs(actual - expected_duration) > DURATION_TOLERANCE:
            return False, f"duration mismatch (expected ~{expected_duration:.0f}s, got ~{actual:.0f}s)"
    emb_artist, emb_title = _read_embedded_artist_title(filepath)
    if _metadata_mismatch(emb_artist, emb_title, artist_name, track_name):
        return False, f"metadata mismatch (got '{emb_artist} - {emb_title}')"
    return True, ""


def _quarantine_file(filepath: str, quarantine_dir: str, reason: str) -> str:
    """Move a mismatched download into the quarantine folder. Returns new path or None."""
    try:
        os.makedirs(quarantine_dir, exist_ok=True)
        dest = os.path.join(quarantine_dir, os.path.basename(filepath))
        if os.path.exists(dest):
            base, ext = os.path.splitext(dest)
            i = 1
            while os.path.exists(f"{base} ({i}){ext}"):
                i += 1
            dest = f"{base} ({i}){ext}"
        shutil.move(filepath, dest)
        logging.warning(f"\U0001F6AB [DOWNLOAD] Quarantined '{os.path.basename(filepath)}' ({reason}) -> {dest}")
        return dest
    except Exception as exc:
        logging.error(f"\U0000274C [DOWNLOAD] Failed to quarantine '{filepath}': {exc}")
        return None


def ensure_local_files(tracks: list, playlist_name: str, music_path: str):
    """
    Ensure all tracks in the list are downloaded locally.

    File structure: MUSIC_PATH/<Playlist>/<Artist>/<Album>/<Artist - Track>.flac|mp3
    """
    if not music_path:
        logging.error("\U0000274C [DOWNLOAD] MUSIC_PATH not specified.")
        return

    logging.debug(f"\U0001F4C2 [{playlist_name}] Checking local files for {len(tracks)} tracks...")

    download_queue = []
    safe_playlist = sanitizeFilename(playlist_name)
    playlist_folder = os.path.join(music_path, safe_playlist)
    quarantine_dir = os.environ.get("QUARANTINE_PATH", "").strip() or os.path.join(music_path, "_quarantine")

    for track in tracks:
        track_name = strip_words(track.get("title", "")) or "Unknown Track"
        artist_name = strip_words(track.get("artist", "")) or "Unknown Artist"
        album_name = normalize_album(strip_words(track.get("album", "")))

        safe_artist = sanitizeFilename(artist_name)
        safe_album = sanitizeFilename(album_name)
        safe_track = sanitizeFilename(track_name)

        album_folder = os.path.join(playlist_folder, safe_artist, safe_album)
        createFolder(album_folder)

        prefer_flac = os.environ.get("PREFER_FLAC", "true").lower() in ["true", "1", "yes"]
        file_ext = "flac" if prefer_flac else "mp3"
        expected_filename = f"{safe_artist} - {safe_track}.{file_ext}"
        expected_filepath = os.path.join(album_folder, expected_filename)

        if track_exists_in_directory(album_folder, safe_track):
            logging.debug(f"\U00002705 [{playlist_name}] Already exists: '{safe_artist} - {safe_track}'")
            continue

        if find_and_rename_track_by_tag(album_folder, artist_name, track_name, expected_filepath):
            logging.debug(f"\U0001F504 [{playlist_name}] Found by metadata, renamed: '{safe_artist} - {safe_track}'")
            continue

        logging.debug(f"\U00002B07\uFE0F  [{playlist_name}] Missing track, queued for download: '{safe_artist} - {safe_track}'")
        duration = track.get("duration")
        download_queue.append((album_folder, track_name, artist_name, album_name, expected_filepath, duration))

    if download_queue:
        logging.info(f"\U0001F4E5 [{playlist_name}] Downloading {len(download_queue)} missing tracks...")
        download_delay = float(os.environ.get("DOWNLOAD_DELAY", "") or "0.1")
        for idx, (output_folder, track_name, artist_name, album_name, expected_filepath, duration) in enumerate(download_queue, 1):
            download_track(output_folder, track_name, artist_name, expected_filepath, playlist_name, album_name, duration, quarantine_dir)
            if idx < len(download_queue):
                time.sleep(download_delay)
        logging.debug(f"\U00002705 [{playlist_name}] Download batch complete ({len(download_queue)} tracks processed)")
    else:
        logging.info(f"\U00002705 [{playlist_name}] All {len(tracks)} tracks already present")


def search_youtube_for_track(artist_name: str, track_name: str) -> Optional[str]:
    """
    Search YouTube for a track and return the URL of the top result.
    Uses an in-memory cache to avoid duplicate queries.
    """
    if not artist_name or not track_name:
        logging.error(f"\U0000274C [YOUTUBE] Invalid input: artist_name='{artist_name}', track_name='{track_name}'")
        return None

    safe_artist = str(artist_name).strip()
    safe_track = str(track_name).strip()
    search_query = f"{safe_artist} - {safe_track}"

    if search_query in youtube_url_cache:
        cached = youtube_url_cache[search_query]
        if cached:
            logging.debug(f"\U0001F4BE [YOUTUBE] Cache hit for '{search_query}'")
        return cached

    logging.debug(f"\U0001F50D [YOUTUBE] Searching for '{search_query}'...")

    try:
        search_cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-playlist",
            "--print", "%(id)s\t%(title)s",
            f"ytsearch8:{search_query}",
        ]
        proc = subprocess.run(search_cmd, capture_output=True, text=True, timeout=30)

        if proc.returncode == 0 and proc.stdout.strip():
            candidates = []
            for line in proc.stdout.strip().split("\n"):
                if "\t" in line:
                    vid, title = line.split("\t", 1)
                    vid, title = vid.strip(), title.strip()
                    if vid and title:
                        candidates.append((vid, title))
            if candidates:
                best_id, best_title, best_score = None, None, 0.0
                for vid, title in candidates:
                    score = _youtube_title_score(title, safe_artist, safe_track)
                    if score > best_score:
                        best_id, best_title, best_score = vid, title, score
                if best_id and best_score >= YOUTUBE_MIN_SCORE:
                    url = f"https://www.youtube.com/watch?v={best_id}"
                    logging.debug(f"\U00002705 [YOUTUBE] Found via yt-dlp: {url} ('{best_title}', score={best_score:.2f})")
                    youtube_url_cache[search_query] = url
                    return url
                logging.debug(f"\u26A0\uFE0F  [YOUTUBE] yt-dlp results failed title match for '{search_query}' (best score {best_score:.2f})")

        logging.debug("\U0001F504 [YOUTUBE] Trying YoutubeSearchPython fallback...")
        videos_search = VideosSearch(safe_artist + " " + safe_track, limit=5)
        search_result = videos_search.result()
        if search_result and isinstance(search_result, dict):
            results = search_result.get("result", [])
            best_url, best_title, best_score = None, None, 0.0
            for video in results:
                if not (video and isinstance(video, dict) and video.get("link")):
                    continue
                title = video.get("title", "") or ""
                score = _youtube_title_score(title, safe_artist, safe_track)
                if score > best_score:
                    best_url, best_title, best_score = video["link"], title, score
            if best_url and best_score >= YOUTUBE_MIN_SCORE:
                logging.debug(f"\U00002705 [YOUTUBE] Found via YoutubeSearchPython: {best_url} ('{best_title}', score={best_score:.2f})")
                youtube_url_cache[search_query] = best_url
                return best_url

        logging.warning(f"\U0000274C [YOUTUBE] No good match for '{search_query}'")
        youtube_url_cache[search_query] = None
        return None

    except subprocess.TimeoutExpired:
        logging.error(f"\U0000274C [YOUTUBE] Search timeout for '{search_query}'")
        youtube_url_cache[search_query] = None
        return None
    except TypeError as e:
        logging.error(f"\U0000274C [YOUTUBE] Type error for '{search_query}': {e}")
        youtube_url_cache[search_query] = None
        return None
    except Exception as e:
        logging.error(f"\U0000274C [YOUTUBE] Search error for '{search_query}': {e}")
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


def build_plex_track_set(plex) -> set:
    """
    Load every track from all Plex music libraries into a set of
    normalized (artist, title) tuples.  Call once per cycle and pass
    the result to functions that need to check track presence.
    """
    track_set: set = set()
    try:
        music_sections = [s for s in plex.library.sections() if s.type == "artist"]
        for section in music_sections:
            for track in section.searchTracks():
                artist = normalize_for_matching(getattr(track, "grandparentTitle", "") or "")
                title = normalize_for_matching(track.title or "")
                if artist or title:
                    track_set.add((artist, title))
        logging.info(f"[PLEX] Built track set: {len(track_set)} tracks across {len(music_sections)} library section(s)")
    except Exception as exc:
        logging.warning(f"[PLEX] Could not build track set: {exc}")
    return track_set


def track_in_plex_library(plex, artist: str, title: str) -> bool:
    """
    Check whether a track exists in any Plex music library by artist and title.
    Uses Plex library search and normalizes both sides for fuzzy matching.
    Returns True if a matching track is found.
    """
    norm_artist = normalize_for_matching(artist)
    norm_title = normalize_for_matching(title)
    try:
        results = plex.library.search(title, mediatype="track")
        for track in results:
            if (normalize_for_matching(track.title) == norm_title and
                    normalize_for_matching(getattr(track, "grandparentTitle", "") or "") == norm_artist):
                return True
    except Exception as exc:
        logging.warning(f"\u26A0\uFE0F  [PLEX] Library search failed for '{artist} - {title}': {exc}")
    return False


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
                    logging.debug(f"Found track by metadata tag: '{filename}'")
                    if current != expected_filepath:
                        logging.warning(f"Renaming '{filename}' to '{os.path.basename(expected_filepath)}'")
                        os.rename(current, expected_filepath)
                    return True
    except FileNotFoundError:
        return False
    except Exception as e:
        logging.error(f"Error processing metadata in '{folder}': {e}")
    return False


def write_audio_metadata(filepath: str, artist: str, title: str, album: str = "") -> bool:
    """
    Overwrite the embedded tags of a downloaded audio file with clean,
    source-of-truth metadata so Plex does not pick up YouTube junk such as
    "Official Video", "VEVO" or "RHINO".

    - Strips YouTube junk words from artist/title/album.
    - Maps missing/placeholder albums ("Unknown Album", "[standalone
      recordings]", ...) to "Single".
    - Clears YouTube-specific tags (synopsis, purl, comment, description).
    """
    if not artist and not title:
        return False
    artist = strip_words(artist)
    title = strip_words(title)
    album = normalize_album(strip_words(album))
    try:
        audio = mutagen.File(filepath, easy=True)
        if audio is None:
            logging.warning(f"\u26A0\uFE0F  [METADATA] Unsupported file for tagging: '{filepath}'")
            return False
        audio["title"] = title
        audio["artist"] = artist
        audio["albumartist"] = artist
        audio["album"] = album
        for key in YOUTUBE_JUNK_TAGS:
            try:
                audio.pop(key, None)
            except Exception:
                pass
        audio.save()
        logging.debug(f"\U0001F3F7\uFE0F  [METADATA] Tagged '{os.path.basename(filepath)}': {artist} - {title}")
        return True
    except Exception as exc:
        logging.warning(f"\u26A0\uFE0F  [METADATA] Failed to tag '{filepath}': {exc}")
        return False


def download_track(output_folder: str, track_name: str, artist_name: str, expected_filepath: str, playlist_name: str = "Unknown", album_name: str = "", expected_duration=None, quarantine_dir: str = None):
    """
    Download a single track using YouTube search + yt-dlp.
    Format is determined by PREFER_FLAC (default: true).

    Validates the download (title match at search time, plus duration and
    embedded-metadata checks after download) and quarantines wrong videos.
    """
    download_stats["downloads_attempted"] += 1
    ytdlp_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    prefer_flac = os.environ.get("PREFER_FLAC", "true").lower() in ["true", "1", "yes"]

    if not quarantine_dir:
        quarantine_dir = os.path.join(output_folder, "_quarantine")

    files_before = set()
    if os.path.exists(output_folder):
        files_before = set(os.listdir(output_folder))

    logging.debug(f"\U0001F50D [{playlist_name}] Searching YouTube for '{artist_name} - {track_name}'...")

    youtube_url = search_youtube_for_track(artist_name, track_name)
    if not youtube_url:
        logging.error(f"\U0000274C [{playlist_name}] No YouTube result for '{artist_name} - {track_name}'")
        track_download_failure(playlist_name, artist_name, track_name)
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

        logging.debug(f"\U0001F4E5 [{playlist_name}] Downloading '{artist_name} - {track_name}'...")
        capture = ytdlp_log_level != "DEBUG"
        proc = subprocess.run(cmd, capture_output=capture, text=True, timeout=300)

        if proc.returncode == 0:
            new_audio = _check_new_audio_files(output_folder, files_before)
            if new_audio:
                for f in new_audio:
                    filepath = os.path.join(output_folder, f)
                    ok, reason = _download_is_valid(filepath, artist_name, track_name, expected_duration)
                    if not ok:
                        _quarantine_file(filepath, quarantine_dir, reason)
                        track_download_failure(playlist_name, artist_name, track_name)
                        return False
                    write_audio_metadata(filepath, artist_name, track_name, album_name)
                    logging.debug(f"\U00002705 [{playlist_name}] Downloaded: {f}")
                track_download_success(playlist_name, artist_name, track_name)
                return True

        if prefer_flac:
            logging.debug(f"\U0001F504 [{playlist_name}] FLAC failed, trying MP3 fallback for '{artist_name} - {track_name}'...")
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
                        filepath = os.path.join(output_folder, f)
                        ok, reason = _download_is_valid(filepath, artist_name, track_name, expected_duration)
                        if not ok:
                            _quarantine_file(filepath, quarantine_dir, reason)
                            track_download_failure(playlist_name, artist_name, track_name)
                            return False
                        write_audio_metadata(filepath, artist_name, track_name, album_name)
                        logging.debug(f"\U00002705 [{playlist_name}] Downloaded (MP3 fallback): {f}")
                    track_download_success(playlist_name, artist_name, track_name)
                    return True

    except subprocess.TimeoutExpired:
        logging.error(f"\U0000274C [{playlist_name}] Download timeout for '{artist_name} - {track_name}'")
    except Exception as e:
        logging.error(f"\U0000274C [{playlist_name}] Download error for '{artist_name} - {track_name}': {e}")

    logging.error(f"\U0000274C [{playlist_name}] All download methods failed for '{artist_name} - {track_name}'")
    track_download_failure(playlist_name, artist_name, track_name)
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
    logging.debug(f"\U0001F5D1\uFE0F  [CLEANUP] Scanning library '{library_name}' for 1-star tracks...")
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
        logging.debug(f"\U0001F5D1\uFE0F  [CLEANUP] Found {len(one_star_tracks)} 1-star tracks in '{library_name}'")
    except Exception as e:
        logging.error(f"\U0000274C [CLEANUP] Error scanning library '{library_name}': {e}")
    return one_star_tracks


def delete_plex_track(track, playlist_name: str = "Unknown"):
    """
    Delete a track from the Plex library and filesystem.
    """
    track_title = track.title
    artist_name = track.artist().title if hasattr(track, 'artist') and track.artist() else "Unknown"
    try:
        track.delete()
        logging.debug(f"\U0001F5D1\uFE0F  [CLEANUP] Deleted from Plex: '{track_title}'")
        track_deletion_success(playlist_name, artist_name, track_title)
    except Exception as e:
        logging.error(f"\U0000274C [CLEANUP] Failed to delete '{track_title}': {e}")
        track_deletion_failure()


download_stats = {
    "downloads_attempted": 0,
    "downloads_successful": 0,
    "downloads_failed": 0,
    "tracks_deleted": 0,
    "delete_failures": 0,
    "downloaded_tracks": [],
    "deleted_tracks": [],
    "failed_tracks": [],
}


def reset_stats():
    global download_stats
    download_stats = {
        "downloads_attempted": 0,
        "downloads_successful": 0,
        "downloads_failed": 0,
        "tracks_deleted": 0,
        "delete_failures": 0,
        "downloaded_tracks": [],
        "deleted_tracks": [],
        "failed_tracks": [],
    }


def track_download_success(playlist="", artist="", track=""):
    download_stats["downloads_successful"] += 1
    if playlist and artist and track:
        download_stats["downloaded_tracks"].append({"playlist": playlist, "artist": artist, "track": track})


def track_download_failure(playlist="", artist="", track=""):
    download_stats["downloads_failed"] += 1
    if playlist and artist and track:
        download_stats["failed_tracks"].append({"playlist": playlist, "artist": artist, "track": track})


def track_deletion_success(library="", artist="", track=""):
    download_stats["tracks_deleted"] += 1
    if library and artist and track:
        download_stats["deleted_tracks"].append({"library": library, "artist": artist, "track": track})


def track_deletion_failure():
    download_stats["delete_failures"] += 1


def print_sync_recap():
    sep = "=" * 52
    lines = [
        "",
        f"\U0001F4CA {sep}",
        "\U0001F4CA  SYNC CYCLE RECAP",
        f"\U0001F4CA {sep}",
        f"  \U0001F4E5 Downloads:  {download_stats['downloads_successful']}/{download_stats['downloads_attempted']} successful",
        f"  \U0001F5D1\uFE0F  Deleted:    {download_stats['tracks_deleted']} tracks",
    ]
    if download_stats["downloads_attempted"] > 0:
        rate = (download_stats["downloads_successful"] / download_stats["downloads_attempted"]) * 100
        lines.append(f"  \U0001F3AF Success Rate: {rate:.1f}%")

    if download_stats["downloaded_tracks"]:
        lines.append("")
        by_playlist = {}
        for entry in download_stats["downloaded_tracks"]:
            by_playlist.setdefault(entry["playlist"], []).append(entry)
        for playlist, entries in by_playlist.items():
            lines.append(f"  \U00002705 [{playlist}] Downloaded:")
            for e in entries:
                lines.append(f"     - {e['artist']} - {e['track']}")

    if download_stats["failed_tracks"]:
        lines.append("")
        by_playlist = {}
        for entry in download_stats["failed_tracks"]:
            by_playlist.setdefault(entry["playlist"], []).append(entry)
        for playlist, entries in by_playlist.items():
            lines.append(f"  \U0000274C [{playlist}] Failed:")
            for e in entries:
                lines.append(f"     - {e['artist']} - {e['track']}")

    if download_stats["deleted_tracks"]:
        lines.append("")
        by_library = {}
        for entry in download_stats["deleted_tracks"]:
            by_library.setdefault(entry["library"], []).append(entry)
        for library, entries in by_library.items():
            lines.append(f"  \U0001F5D1\uFE0F  [CLEANUP] Deleted from '{library}':")
            for e in entries:
                lines.append(f"     - {e['artist']} - {e['track']}")

    if not any([download_stats["downloaded_tracks"], download_stats["failed_tracks"], download_stats["deleted_tracks"]]):
        lines.append("")
        lines.append("  \U00002705 Nothing to do - all playlists up to date.")

    lines.append(f"\U0001F4CA {sep}")
    logging.info("\n".join(lines))
