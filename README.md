# Plex-Track-Manager

Plex-Track-Manager syncs your Plex listening habits to Last.fm, generates **Discover Weekly** and **Release Radar** playlists from Last.fm recommendations, and downloads tracks using **yt-dlp**. Files are organized for seamless Plex Smart Playlist integration.

---

## How it works

1. **Plex -> Last.fm sync**: At each cycle the app reads your Plex libraries, loves highly-rated tracks on Last.fm and scrobbles your recent play history.
2. **Discover Weekly**: Using your Last.fm profile the app finds similar artists you don't listen to yet and picks their top tracks (max 20 by default).
3. **Release Radar**: The app queries MusicBrainz for recent releases (last 30 days) from your favourite artists and collects the track listings.
4. **Download**: Missing tracks are downloaded from YouTube via yt-dlp (FLAC preferred, MP3 fallback).
5. **1-Star cleanup**: Tracks you rate 1-star in Plex are deleted from the library and filesystem.
6. **Plex Smart Playlists** automatically pick up the new files based on folder path filters.

---

## Features

- **Last.fm integration** - Syncs loved tracks and scrobbles from Plex to Last.fm
- **Discover Weekly** - Recommended tracks from similar artists (configurable count)
- **Release Radar** - New releases from your favourite artists via MusicBrainz
- **High-quality downloads** - FLAC preferred, MP3 fallback via yt-dlp
- **Smart file organization** - `MUSIC_PATH/<Playlist>/<Artist>/<Album>/<Artist - Track>.flac`
- **Intelligent caching** - Checks for existing FLAC/MP3 before downloading
- **Metadata tagging** - Automatic artist, track and album tags via yt-dlp
- **1-Star rating cleanup** - Delete unwanted tracks from Plex and disk
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
| `SYNC_FULL_HISTORY` | On first run, scrobble entire Plex history to Last.fm (`true`/`false`). When `false`, only future plays are synced. | No | `false` |

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
  -v /path/to/your/music:/music \
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

The app auto-detects all music-type libraries in Plex and scans each one.

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
