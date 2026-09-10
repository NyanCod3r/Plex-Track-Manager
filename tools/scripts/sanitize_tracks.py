#!/usr/bin/env python3
"""
sanitize_tracks.py - Clean up yt-dlp metadata / naming junk in the music library.

1. Walks the music folder and every subfolder looking for audio files (.flac/.mp3).
2. Only proposes a change when a trigger word (default "vevo"/"rhino") is found
   - case-insensitively - in the file NAME or embedded METADATA.
3. Strips a configurable list of junk words ("official video", "official audio",
   "vevo", "rhino", ...) from the names "with nothing".
4. Re-pulls canonical metadata (artist/title/album) from MusicBrainz - the same
   database ListenBrainz references - so tags come from the source.
5. When a track appears on several releases, lets you choose album vs single.
6. Lets you choose the folder structure, and normalises file/folder names with no
   special characters (AC/DC -> ACDC, rain_dead -> Rain Dead).

Usage:
    python3 sanitize_tracks.py                     # dry-run, interactive
    python3 sanitize_tracks.py --apply             # move + retag
    python3 sanitize_tracks.py --apply --yes       # auto-confirm (still asks albums)
    python3 sanitize_tracks.py --structure artist
    python3 sanitize_tracks.py --root /path/to/music

Requires: mutagen, requests.
"""

import argparse
import logging
import os
import re
import shutil
import sys
import time

import mutagen
import requests

# ---------------------------------------------------------------------------
# CONFIG - edit these to taste
# ---------------------------------------------------------------------------

# Only propose cleanup when one of these words appears in name or metadata.
# "youtube"/"youtu.be" catch any file that still has the YouTube URL in its
# purl/description/synopsis tags (yt-dlp leaves it there on every download).
TRIGGER_WORDS = [
    "vevo",
    "rhino",
    "official video",
    "official audio",
    "official lyric video",
    "official hd video",
    "official teaser video",
    "official trailer video",
    "youtube",
    "youtu.be",
    "Pt. 1",
    "Pt. 2",
    "Pt. 3"
]

# Words/phrases stripped "with nothing" from titles/artists/albums.
# Longer phrases are matched first automatically.
STRIP_WORDS = [
    "official music video",
    "official lyric video",
    "official audio video",
    "official hd video",
    "official video",
    "official audio",
    "lyric video",
    "music video",
    "vevo",
    "rhino",
    "deluxe",
    "remastered",
    "bonus track",
    "bonus tracks",
    "deluxe edition",
    "remastered edition",
    "original",
    "original edition"
]

AUDIO_EXTS = (".flac", ".mp3")

# Tags that hold YouTube junk (video description / URL) and are cleared on save.
YOUTUBE_JUNK_TAGS = ("comment", "description", "synopsis", "purl")

MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
USER_AGENT = "plex-track-manager-sanitizer/1.0 (https://github.com/NyanCod3r/Plex-Track-Manager)"
MB_RATE_LIMIT = 1.0  # seconds between MusicBrainz requests

# Folder structures (relative to the playlist folder the track is in):
FOLDER_STRUCTURES = {
    "artist_album": "Artist/Album/Artist - Title.ext",
    "artist": "Artist/Artist - Title.ext",
    "flat": "Artist - Title.ext",
}

log = logging.getLogger("sanitize")


def setup_logging(verbose=False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def ask(prompt, default=None):
    """Prompt the user and return the answer (or the default on empty/EOF input)."""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    try:
        raw = input()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return raw.strip() if raw.strip() else default


def _smart_title(word):
    """Capitalise a word but preserve all-caps acronyms (ACDC, ABBA, ...)."""
    if not word:
        return word
    if word.isupper():
        return word
    return word[0].upper() + word[1:].lower()


def sanitize_name(name):
    """
    Make a name safe for a file/folder, with no special characters.
    - "_" becomes a space     -> "rain_dead" -> "Rain Dead"
    - "/" and "\\" are removed -> "AC/DC"    -> "ACDC"
    - other invalid characters are removed and words are title-cased.
    """
    if not name:
        return ""
    name = str(name).strip()
    name = name.replace("_", " ")
    name = name.replace("/", "").replace("\\", "")
    for ch in '<>:"|?*':
        name = name.replace(ch, "")
    words = re.split(r"\s+", name)
    return " ".join(_smart_title(w) for w in words if w)


def strip_words(text):
    """Remove every configured junk word/phrase from `text` and clean leftovers."""
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


# Album names that are not a real album. These are auto-corrected to "Single"
# (so the folder becomes Artist/Single/...) without asking.
SINGLE_ALIASES = {
    "standalone recordings",
    "standalone recording",
    "non-album tracks",
    "non-album track",
    "unknown album",
    "unknownalbum",
}


def normalize_album(album):
    """Map '[standalone recordings]' and friends to 'Single'; otherwise return as-is."""
    if not album:
        return ""
    key = str(album).strip().strip("[]").strip().lower()
    if key in SINGLE_ALIASES:
        return "Single"
    return str(album).strip()


_COMMON_WORDS = {
    "the", "a", "an", "and", "of", "in", "on", "at", "to", "for",
    "is", "are", "it", "with", "feat", "ft", "vs",
}


def _significant_words(text):
    """Lowercase word tokens after stripping junk, minus common filler words."""
    words = set(re.findall(r"[a-z0-9]+", strip_words(text or "").lower()))
    return words - _COMMON_WORDS


def radical_mismatch(old_artist, old_title, new_artist, new_title):
    """
    True when the original artist/title share no meaningful words with the
    corrected values - a strong sign the downloaded audio is a different video
    than the requested track (e.g. a news clip instead of the song).
    """
    old_a = _significant_words(old_artist)
    old_t = _significant_words(old_title)
    new_a = _significant_words(new_artist)
    new_t = _significant_words(new_title)
    return not (old_a & new_a) and not (old_t & new_t)


# ---------------------------------------------------------------------------
# Tag reading / writing
# ---------------------------------------------------------------------------


def read_tags(path):
    try:
        audio = mutagen.File(path, easy=True)
    except Exception as exc:
        log.warning("Could not read '%s': %s", path, exc)
        return None
    if audio is None:
        return {}
    tags = {}
    try:
        for key in audio.keys():
            tags[key] = audio.get(key, [])
    except Exception:
        for key in ("title", "artist", "album", "albumartist", "comment", "description"):
            try:
                tags[key] = audio.get(key, [])
            except Exception:
                pass
    return tags


def write_tags(path, artist, title, album):
    try:
        audio = mutagen.File(path, easy=True)
        if audio is None:
            log.warning("Unsupported file, cannot tag: '%s'", path)
            return False
        audio["title"] = title
        audio["artist"] = artist
        audio["albumartist"] = artist
        if album:
            audio["album"] = album
        for key in YOUTUBE_JUNK_TAGS:
            try:
                audio.pop(key, None)
            except Exception:
                pass
        audio.save()
        return True
    except Exception as exc:
        log.warning("Failed to write tags for '%s': %s", path, exc)
        return False


# ---------------------------------------------------------------------------
# Trigger detection + query derivation
# ---------------------------------------------------------------------------


def find_triggers(path, tags):
    """Return [(word, source), ...] for every trigger word found in name or tags."""
    hits = []
    fn = os.path.basename(path).lower()
    for word in TRIGGER_WORDS:
        if word in fn:
            hits.append((word, "filename"))
    for key, values in tags.items():
        for value in values:
            low = str(value).lower()
            for word in TRIGGER_WORDS:
                if word in low:
                    hits.append((word, f"tag '{key}'"))
    return hits


def derive_query(path, tags):
    """
    Return a (artist, title) tuple to feed MusicBrainz.
    The filename is usually already clean ("Artist - Title.ext"), so prefer it;
    otherwise fall back to the tags.
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    if " - " in stem:
        artist, title = [part.strip() for part in stem.split(" - ", 1)]
        return strip_words(artist.replace("_", " ")), strip_words(title.replace("_", " "))

    artist = strip_words((tags.get("artist") or [""])[0] or "")
    title = strip_words((tags.get("title") or [""])[0] or "")
    # Tags often contain "Artist - Title (Official Video)"; drop the artist prefix.
    if artist and title.lower().startswith(artist.lower() + " - "):
        title = title[len(artist) + 3:].strip()
    return artist, title


# ---------------------------------------------------------------------------
# MusicBrainz lookups (the canonical source ListenBrainz references)
# ---------------------------------------------------------------------------

_last_mb_request = 0.0
_canonical_cache = {}


def _mb_get(path, params):
    global _last_mb_request
    for attempt in range(3):
        elapsed = time.time() - _last_mb_request
        if elapsed < MB_RATE_LIMIT:
            time.sleep(MB_RATE_LIMIT - elapsed)
        try:
            resp = requests.get(
                f"{MUSICBRAINZ_API}{path}",
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=25,
            )
            _last_mb_request = time.time()
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            _last_mb_request = time.time()
            log.debug("MusicBrainz request failed (attempt %d, %s): %s", attempt + 1, path, exc)
            time.sleep(1.5)
    return None


def _search_recordings(query, limit=10):
    data = _mb_get(
        "/recording/",
        {"query": query, "fmt": "json", "limit": limit,
         "inc": "artist-credits+releases+release-groups"},
    )
    return (data or {}).get("recordings", [])


def _first_artist_name(rec):
    ac = rec.get("artist-credit") or []
    if ac:
        return ac[0].get("name") or (ac[0].get("artist") or {}).get("name") or ""
    return ""


_TYPE_ORDER = {"Album": 0, "Single": 1, "EP": 2}


def _collect_release_groups(recordings):
    """
    Extract a deduped, ordered list of {album, type, date} from recordings,
    skipping compilations / soundtracks / live noise that is rarely the "real"
    album for the track.
    """
    options = []
    seen = set()
    for rec in recordings:
        for rel in rec.get("releases", []):
            rg = rel.get("release-group") or {}
            album = rg.get("title") or rel.get("title") or ""
            ptype = rg.get("primary-type") or "unknown"
            secondary = rg.get("secondary-types") or []
            date = rg.get("first-release-date") or rel.get("first-release-date") or ""
            if not album:
                continue
            if normalize_album(album) == "Single":
                album = "Single"
                ptype = "Single"
            if ptype not in _TYPE_ORDER:
                continue
            if "Compilation" in secondary or "Soundtrack" in secondary:
                continue
            key = (album.lower(), ptype)
            if key in seen:
                continue
            seen.add(key)
            options.append({"album": album, "type": ptype, "date": (date or "")[:4]})
    options.sort(key=lambda o: (_TYPE_ORDER.get(o["type"], 9), o["date"] or "9999"))
    return options


def canonical_metadata(artist, title):
    """
    Resolve canonical {artist, title, options} from MusicBrainz (the database
    ListenBrainz references). Returns None when nothing can be found.
    """
    key = (artist.lower(), title.lower())
    if key in _canonical_cache:
        return _canonical_cache[key]

    result = None
    # A single plain search is fast; higher limit surfaces both the album and
    # any single release-group for the "album vs single" choice.
    recs = _search_recordings(f'recording:"{title}" AND artist:"{artist}"', limit=25)
    if recs:
        canon_title = recs[0].get("title") or title
        canon_artist = ""
        for rec in recs:
            canon_artist = _first_artist_name(rec)
            if canon_artist:
                break

        options = _collect_release_groups(recs)
        result = {"artist": canon_artist or artist, "title": canon_title or title, "options": options}

    _canonical_cache[key] = result
    return result


# ---------------------------------------------------------------------------
# Interactive choice helpers
# ---------------------------------------------------------------------------


def choose_structure(default="artist_album"):
    print("\nChoose a folder structure (relative to each playlist folder):")
    for i, (key, desc) in enumerate(FOLDER_STRUCTURES.items(), 1):
        print(f"  {i}. {key:<13} -> {desc}")
    print("     (artist_album is the current Artist/Album/Track layout)")
    while True:
        ans = ask(f"Structure [{default}]: ", default)
        if ans in FOLDER_STRUCTURES:
            return ans
        if ans.isdigit() and 1 <= int(ans) <= len(FOLDER_STRUCTURES):
            return list(FOLDER_STRUCTURES)[int(ans) - 1]
        print("  Invalid choice.")


def choose_album(options, current_album, artist, title):
    """
    Pick the album for a track. Returns (album, type).

    If the track already has a meaningful album (from its tag or folder) it is
    kept unchanged. Only when there is no existing album do we consult
    MusicBrainz and, if genuinely ambiguous, ask to choose album vs single.
    """
    cur = strip_words(current_album) or ""
    if cur:
        return cur, "keep"

    if not options:
        return "Unknown Album", "unknown"
    if len(options) == 1:
        opt = options[0]
        return opt["album"], opt["type"]

    print(f"\n  Ambiguous - '{artist} - {title}' has no album and matches several releases:")
    for i, opt in enumerate(options, 1):
        date = f", {opt['date']}" if opt["date"] else ""
        print(f"    {i}. {opt['album']}  [{opt['type']}{date}]")
    print("    s. Treat as a single (no album folder)")
    print("    c. Enter a custom album name")
    while True:
        ans = ask("  Choose album: ", "1").lower()
        if ans == "s":
            return "", "single"
        if ans == "c":
            custom = ask("  Album name: ", "")
            return strip_words(custom) or "Unknown Album", "custom"
        if ans.isdigit() and 1 <= int(ans) <= len(options):
            opt = options[int(ans) - 1]
            return opt["album"], opt["type"]
        print("    Invalid choice.")


# ---------------------------------------------------------------------------
# Path building / file moves
# ---------------------------------------------------------------------------


def playlist_base(root, path):
    """Return the top-level folder (the 'playlist') that contains `path`."""
    rel = os.path.relpath(path, root)
    parts = rel.split(os.sep)
    if parts and parts[0] not in (".", ".."):
        return os.path.join(root, parts[0])
    return os.path.dirname(path)


def current_album_hint(root, path):
    """
    Guess the current album from the folder layout <playlist>/<artist>/<album>/<file>.
    Returns '' when there is no album folder.
    """
    rel = os.path.relpath(path, root)
    parts = rel.split(os.sep)
    if len(parts) >= 4:
        return parts[-2]
    return ""


def build_new_path(base, structure, artist, title, album, ext):
    artist = sanitize_name(artist) or "Unknown Artist"
    title = sanitize_name(title) or "Unknown Title"
    filename = f"{artist} - {title}{ext}"
    if structure == "flat":
        return os.path.join(base, filename)
    if structure == "artist" or not album:
        return os.path.join(base, artist, filename)
    album = sanitize_name(album) or "Unknown Album"
    return os.path.join(base, artist, album, filename)


def move_file(src, dst):
    if os.path.abspath(src) == os.path.abspath(dst):
        return src
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        base, ext = os.path.splitext(dst)
        i = 1
        while os.path.exists(f"{base} ({i}){ext}"):
            i += 1
        dst = f"{base} ({i}){ext}"
    shutil.move(src, dst)
    return dst


# ---------------------------------------------------------------------------
# Per-track processing + main loop
# ---------------------------------------------------------------------------


def process_track(path, root, structure, apply_changes, auto_yes, stats):
    ext = os.path.splitext(path)[1].lower()
    tags = read_tags(path)
    if tags is None:
        stats["unreadable"] += 1
        return None

    hits = find_triggers(path, tags)
    if not hits:
        return None
    triggered = {}
    for word, source in hits:
        triggered.setdefault(word, source)

    q_artist, q_title = derive_query(path, tags)
    if not q_title:
        log.warning("Skipping '%s' (could not derive a title)", path)
        stats["skipped"] += 1
        return None

    canon = canonical_metadata(q_artist, q_title)
    if canon and canon.get("artist") and canon.get("title"):
        artist = canon["artist"]
        title = canon["title"]
        options = canon["options"]
        src = "MusicBrainz"
    else:
        artist = q_artist
        title = q_title
        options = []
        src = "local (no MusicBrainz match)"

    raw_album = (tags.get("album") or [""])[0]
    if not raw_album:
        raw_album = current_album_hint(root, path)
    current_album = normalize_album(raw_album)
    album, album_type = choose_album(options, current_album, artist, title)
    album = normalize_album(album)

    base = playlist_base(root, path)
    new_path = build_new_path(base, structure, artist, title, album, ext)

    old_artist = (tags.get("artist") or [""])[0]
    old_title = (tags.get("title") or [""])[0]
    mismatch = radical_mismatch(old_artist, old_title, artist, title)

    print("\n" + "=" * 78)
    print(f"  {os.path.relpath(path, root)}")
    trigger_desc = ", ".join(f"{w} (in {src})" for w, src in triggered.items())
    print(f"  Triggered by: {trigger_desc}")
    print(f"  Metadata source: {src}")
    print(f"  OLD  artist: {old_artist}")
    print(f"  OLD  title : {old_title}")
    print(f"  OLD  album : {raw_album}")
    print(f"  NEW  artist: {artist}")
    print(f"  NEW  title : {title}")
    print(f"  NEW  album : {album or '(single / none)'}  [{album_type}]")
    print(f"  NEW  path  : {os.path.relpath(new_path, root)}")
    if mismatch:
        print("  \u26A0\uFE0F  WARNING: original artist/title share no words with this track -")
        print("      the audio may be the WRONG video (e.g. a news clip), not this song.")
        print("      Re-tagging is skipped; verify or delete this file manually.")

    if not apply_changes:
        stats["preview"] += 1
        return None

    if mismatch:
        stats["flagged"] += 1
        print("  -> skipped (possible wrong audio - verify/delete manually)")
        return None

    if not auto_yes:
        ans = ask("  Apply? [y]es / [n]o / [s]kip / [q]uit: ", "n").lower()
        if ans == "q":
            return "quit"
        if ans != "y":
            stats["skipped"] += 1
            return None

    ok = write_tags(path, artist, title, album)
    try:
        moved = move_file(path, new_path)
    except Exception as exc:
        log.warning("Failed to move '%s': %s", path, exc)
        stats["errors"] += 1
        return None

    stats["applied"] += 1
    rel_dst = os.path.relpath(moved, root)
    if os.path.abspath(moved) == os.path.abspath(path):
        print(f"  -> tags cleaned (no move needed): {rel_dst}")
    else:
        print(f"  -> {'tagged and moved' if ok else 'moved (tag write failed)'} to: {rel_dst}")
    return None


def main():
    parser = argparse.ArgumentParser(description="Sanitise yt-dlp metadata/naming junk in the music library.")
    parser.add_argument("--root", default=os.path.dirname(os.path.abspath(__file__)),
                        help="Music root folder (default: this script's folder).")
    parser.add_argument("--structure", choices=list(FOLDER_STRUCTURES),
                        help="Folder structure (default: ask interactively).")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run).")
    parser.add_argument("--yes", action="store_true", help="Auto-confirm non-ambiguous changes.")
    parser.add_argument("--verbose", action="store_true", help="Debug logging.")
    args = parser.parse_args()

    setup_logging(args.verbose)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        log.error("Music root does not exist: %s", root)
        return 1

    structure = args.structure or choose_structure()
    mode = "APPLY" if args.apply else "DRY-RUN (no changes written)"
    print(f"\nRoot: {root}")
    print(f"Structure: {structure}  ->  {FOLDER_STRUCTURES[structure]}")
    print(f"Mode: {mode}")
    print(f"Trigger words: {', '.join(TRIGGER_WORDS)}")
    if not args.apply:
        print("Hint: run with --apply to actually move + retag files.\n")

    files = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith(AUDIO_EXTS):
                files.append(os.path.join(dirpath, fn))
    files.sort()

    stats = {"applied": 0, "preview": 0, "skipped": 0, "flagged": 0, "unreadable": 0, "errors": 0}
    print(f"Scanning {len(files)} audio file(s)...\n")

    for path in files:
        try:
            if process_track(path, root, structure, args.apply, args.yes, stats) == "quit":
                print("\nQuit requested.")
                break
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        except Exception as exc:
            log.error("Error processing '%s': %s", path, exc)
            stats["errors"] += 1

    print("\n" + "=" * 78)
    print("Summary")
    print("=" * 78)
    if args.apply:
        print(f"  Applied : {stats['applied']}")
    else:
        print(f"  Previewed (dry-run): {stats['preview']}")
    print(f"  Skipped : {stats['skipped']}")
    print(f"  Flagged : {stats['flagged']}")
    print(f"  Errors  : {stats['errors']}")
    if stats["unreadable"]:
        print(f"  Unreadable files: {stats['unreadable']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
