# Plex-Track-Manager

Plex-Track-Manager syncs your Plex listening habits to Last.fm, generates **Discover Weekly** and **Release Radar** playlists from Last.fm recommendations, and downloads tracks using **yt-dlp**. Files are organized for seamless Plex Smart Playlist integration.

---

## How it works

1. **Plex -> Last.fm sync**: At each cycle the app reads your Plex libraries, loves highly-rated tracks on Last.fm and scrobbles your recent play history.
2. **Discover Weekly**: Using your Last.fm profile the app finds similar artists you don't listen to yet and picks their top tracks (max 20 by default).
3. **Release Radar**: The app queries MusicBrainz for recent releases (last 30 days) from your favourite artists and collects the track listings.
4. **Download**: Missing tracks are downloaded from YouTube via yt-dlp (FLAC preferred, MP3 fallback).
5. **ListenBrainz sync**: Plex playlists are pushed to ListenBrainz. Tracks in your LB playlists that are missing from Plex are downloaded automatically.
6. **1-Star cleanup**: Tracks you rate 1-star in Plex are deleted from the library, filesystem, and all ListenBrainz playlists they appear in.
7. **Plex Smart Playlists** automatically pick up the new files based on folder path filters.

---

## Features

- **Last.fm integration** - Syncs loved tracks and scrobbles from Plex to Last.fm
- **Discover Weekly** - Recommended tracks from similar artists (configurable count)
- **Release Radar** - New releases from your favourite artists via MusicBrainz
- **High-quality downloads** - FLAC preferred, MP3 fallback via yt-dlp
- **Smart file organization** - `MUSIC_PATH/<Playlist>/<Artist>/<Album>/<Artist - Track>.flac`
- **Intelligent caching** - Checks for existing FLAC/MP3 before downloading
- **Metadata tagging** - Automatic artist, track and album tags via yt-dlp
- **ListenBrainz integration** - Syncs Plex playlists to ListenBrainz and downloads tracks missing from Plex
- **1-Star rating cleanup** - Delete unwanted tracks from Plex, disk, and all ListenBrainz playlists
- **Continuous sync** - Runs in a loop with configurable wait time
- **Docker support** - Ready-to-use container

---

## Configuration

| Variable | Description | Required | Default |
| :--- | :--- | :--- | :--- |
| `PLEX_URL` | Full URL for your Plex server (e.g. `http://localhost:32400`). | Yes | |
| `PLEX_TOKEN` | Your Plex authentication token. | Yes | |
| `MUSIC_PATH` | Absolute path where music files are stored/downloaded. | Yes | `/music` |
| `LASTFM_API_KEY` | Your Last.fm API key. | Yes | |
| `LASTFM_API_SECRET` | Your Last.fm API secret. | Yes | |
| `LASTFM_USERNAME` | Your Last.fm username. | Yes | |
| `LASTFM_PASSWORD` | Your Last.fm password. | Yes | |
| `PREFER_FLAC` | Download FLAC when available, MP3 fallback (`true`/`false`). | No | `true` |
| `SECONDS_TO_WAIT` | Seconds between sync cycles. | No | `3600` |
| `LOG_LEVEL` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | No | `INFO` |
| `DOWNLOAD_DELAY` | Seconds between track downloads. | No | `0.1` |
| `MAX_DISCOVER_TRACKS` | Maximum tracks in Discover Weekly playlist. | No | `20` |
| `MAX_RADAR_TRACKS` | Maximum tracks in Release Radar playlist. | No | `20` |
| `RADAR_DAYS_BACK` | How many days back to check for new releases. | No | `30` |
| `RECOMMENDATION_COOLDOWN_DAYS` | Days before a previously recommended track can appear again in Discover Weekly or Release Radar. | No | `90` |
| `SYNC_FULL_HISTORY` | On first run, scrobble entire Plex history to Last.fm (`true`/`false`). When `false`, only future plays are synced. | No | `true` |
| `SYNC_STATE_FILE` | Path to the JSON file that stores sync state (scrobble timestamp, loved hashes, recommendation history). Must be on a persistent volume in Docker. | No | `/data/lastfm_sync_state.json` |
| `LISTENBRAINZ_TOKEN` | Your ListenBrainz user token. If not set, all LB steps are skipped. | No | |
| `LISTENBRAINZ_USERNAME` | Your ListenBrainz username. Required when token is set. | No | |
| `PLEX_PLAYLISTS_JSON` | Path to a `plex_playlists.json` seed file used as an additional playlist source. | No | `/app/src/plex_playlists.json` |
| `UNMATCHED_TRACKS_JSON` | Path to save tracks that could not be matched to a MusicBrainz MBID. Set to a path on a persistent volume to review later. | No | |
| `MB_CACHE_FILE` | Path to persist the MusicBrainz MBID lookup cache between runs. Speeds up sync after the first cycle. Must be on a persistent volume in Docker. | No | `/data/mb_cache.json` |

### Getting your ListenBrainz token

1. Log in at [ListenBrainz](https://listenbrainz.org)
2. Go to **Settings** -> **Music Services & API** -> **User API Token**
3. Copy the token value

### Getting your Last.fm API credentials

1. Go to [Last.fm API](https://www.last.fm/api/account/create)
2. Create a new application (name and description can be anything)
3. Copy your **API Key** and **Shared Secret**
4. Use your regular Last.fm username and password for authentication

### Getting your Plex token

1. Open Plex Web UI
2. Play any media item
3. Click the three-dot menu -> "Get Info" -> "View XML"
4. Look for `X-Plex-Token=` in the URL
5. Copy the token value

---

## Usage

### Local

````bash
export PLEX_URL="http://localhost:32400"
export PLEX_TOKEN="your_plex_token"
export MUSIC_PATH="/data/Music"
export LASTFM_API_KEY="your_api_key"
export LASTFM_API_SECRET="your_api_secret"
export LASTFM_USERNAME="your_username"
export LASTFM_PASSWORD="your_password"

python src/main.py
````

### Docker

````bash
docker run -d \
  --name=plex-track-manager \
  -e PLEX_URL="http://plex:32400" \
  -e PLEX_TOKEN="your_plex_token" \
  -e MUSIC_PATH="/music" \
  -e LASTFM_API_KEY="your_api_key" \
  -e LASTFM_API_SECRET="your_api_secret" \
  -e LASTFM_USERNAME="your_username" \
  -e LASTFM_PASSWORD="your_password" \
  -e PREFER_FLAC="true" \
  -e LOG_LEVEL="INFO" \
  -e LISTENBRAINZ_TOKEN="your_lb_token" \
  -e LISTENBRAINZ_USERNAME="your_lb_username" \
  -e UNMATCHED_TRACKS_JSON="/data/unmatched_tracks.json" \
  -e MB_CACHE_FILE="/data/mb_cache.json" \
  -v /path/to/your/music:/music \
  -v /path/to/data:/data \
  nyancod3r/plex-track-manager:latest
````

---

## Setting up Plex Smart Playlists

One-time setup per playlist:

1. In Plex Web UI go to **Music** -> **Playlists** -> **+ New Playlist** -> **Smart Playlist**
2. Configure filters:
   - **Type**: `Music`
   - **Folder** -> **contains** -> `<MUSIC_PATH>/Discover Weekly`
3. Save the playlist
4. Repeat for `Release Radar`

As Plex-Track-Manager downloads new tracks your Smart Playlists auto-update.

---

## File Organization

````
MUSIC_PATH/
  Discover Weekly/
    Kyuss/
      Blues for the Red Sun/
        Kyuss - Thumb.flac
    Rival Sons/
      Great Western Valkyrie/
        Rival Sons - Electric Man.flac
  Release Radar/
    All Them Witches/
      Nothing as the Ideal/
        All Them Witches - Saturnine & Iron Jaw.flac
````

Structure:
1. `MUSIC_PATH` - root music folder
2. Playlist name (`Discover Weekly` or `Release Radar`)
3. Artist name from track metadata
4. Album name from track metadata
5. Track file: `Artist - Track.flac` (or `.mp3`)

---

## 1-Star Rating Cleanup

When you rate a track 1-star (2 thumbs down) in Plex, Plex-Track-Manager will:
1. Detect the 1-star rating during the next sync cycle
2. Delete the track from your Plex library
3. Delete the local file from the filesystem
4. Remove the track from every ListenBrainz playlist it appears in (requires `LISTENBRAINZ_TOKEN`)

If the ListenBrainz removal fails, a `CRITICAL` log entry is written and the container keeps running. Check logs and remove the track manually on [ListenBrainz](https://listenbrainz.org) if this happens.

The app auto-detects all music-type libraries in Plex and scans each one.

---

## ListenBrainz Playlist Sync

When `LISTENBRAINZ_TOKEN` and `LISTENBRAINZ_USERNAME` are set, every sync cycle will:

1. Read playlists from the live Plex server (and optionally from `PLEX_PLAYLISTS_JSON`)
2. Create any playlist on ListenBrainz that does not exist yet
3. Add any tracks missing from an existing ListenBrainz playlist
4. Check every track in every ListenBrainz playlist against your Plex library
5. Download any tracks not found in Plex via yt-dlp

Tracks are matched to MusicBrainz recording MBIDs before being added to ListenBrainz. Tracks with no MBID match are skipped and optionally saved to `UNMATCHED_TRACKS_JSON` for manual review.

Duplicate detection uses MBIDs rather than artist/title strings, so tracks imported from Spotify or other sources (which may use canonical MusicBrainz artist names) are correctly recognised as already present and not re-added.

MBID lookups are cached in memory and optionally persisted to `MB_CACHE_FILE`. The first sync cycle performs one MusicBrainz API request per track (rate-limited to 1 req/sec). Subsequent cycles skip already-cached lookups, making sync significantly faster.

---

## Troubleshooting

### Files not appearing in Plex

- Verify `MUSIC_PATH` matches your Plex library path
- Trigger a manual library scan in Plex
- Check file permissions (Plex user needs read access)
- Verify Smart Playlist filter matches the folder path

### Download timeouts

- Check your internet connection
- Verify yt-dlp is installed: `yt-dlp --version`
- Test a manual download: `yt-dlp "ytsearch:Artist - Track Name"`
- Set `LOG_LEVEL=DEBUG` for detailed output

### No recommendations generated

- Make sure your Last.fm profile has listening data
- Check that Plex has play history (Settings -> Manage Libraries -> show activity)
- Increase `RADAR_DAYS_BACK` if Release Radar is empty
- Run with `LOG_LEVEL=DEBUG` to see Last.fm API responses

### Last.fm sync issues

- Verify your credentials: log in at last.fm with the same username/password
- Check your API key is valid at [Last.fm API](https://www.last.fm/api)
- Make sure your Plex libraries have music-type sections

---

## Requirements

- Python 3.11+
- `plexapi` (Plex server integration)
- `pylast` (Last.fm API client)
- `musicbrainzngs` (MusicBrainz API for release detection)
- `yt-dlp` (YouTube downloader, system package)
- `youtube-search-python` (YouTube search)
- `mutagen` (Audio metadata handling)
- `requests` (ListenBrainz and MusicBrainz API calls)

Install with:

````bash
pip install -r requirements.txt
````

---

## Migration from Plexify (v3.x)

**Removed:**
- All Spotify integration (`spotipy`, `spotdl`, `SPOTIPY_*` env vars, `SPOTIFY_*` env vars)
- Spotify playlist syncing
- Spotify track removal from playlists
- `generate_spotify_token.py`

**New:**
- Last.fm integration for music taste profiling
- MusicBrainz integration for new release detection
- Auto-generated Discover Weekly and Release Radar playlists
- Plex play history scrobbling to Last.fm
- Automatic loved-track sync from Plex to Last.fm

**What stays the same:**
- yt-dlp download engine
- File organization structure (`<Playlist>/<Artist>/<Album>/<Track>`)
- FLAC/MP3 preference
- 1-star rating cleanup (now Plex + filesystem only, no Spotify)
- Plex Smart Playlist approach
- Docker deployment

**Migration steps:**
1. Remove all `SPOTIPY_*` and `SPOTIFY_*` environment variables
2. Create a Last.fm account and API key
3. Add `LASTFM_API_KEY`, `LASTFM_API_SECRET`, `LASTFM_USERNAME`, `LASTFM_PASSWORD`
4. Delete old cache files (`spotify_playlists.json`)
5. Create Plex Smart Playlists for `Discover Weekly` and `Release Radar`
6. Existing downloaded music files are unaffected

---

## Support

For issues, feature requests, or questions:
- GitHub Issues: [NyanCod3r/Plex-Track-Manager](https://github.com/NyanCod3r/Plex-Track-Manager/issues)
