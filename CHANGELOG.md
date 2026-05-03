# Changelog

## [0.6.5](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.6.4...v0.6.5) (2026-05-03)


### Bug Fixes

* use MBID-primary check for LB missing tracks; skip text match for app-synced playlists[patch] ([f3dacd2](https://github.com/NyanCod3r/Plex-Track-Manager/commit/f3dacd21919e20a42ae6db86ea9c85e112a61068))

## [0.6.4](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.6.3...v0.6.4) (2026-05-03)


### Bug Fixes

* fetch LB playlist metadata when checking for tracks missing from Plex ([aebc749](https://github.com/NyanCod3r/Plex-Track-Manager/commit/aebc7494f5c87df2aa9c5f85898a503f4701dade))

## [0.6.3](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.6.2...v0.6.3) (2026-05-03)


### Bug Fixes

* log per-playlist result of LB missing-track check at INFO level ([e468eef](https://github.com/NyanCod3r/Plex-Track-Manager/commit/e468eef22baf8481f0e4df6623eaa18332f93201))

## [0.6.2](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.6.1...v0.6.2) (2026-05-03)


### Bug Fixes

* skip LB tracks with empty artist/title in missing-track check ([a8f6ef4](https://github.com/NyanCod3r/Plex-Track-Manager/commit/a8f6ef4a67f8e82802f954fa7d73c2ca488af2ad))

## [0.6.1](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.6.0...v0.6.1) (2026-05-03)


### Performance Improvements

* build Plex track set once per cycle for O(1) LB missing-track checks; fix: add 429 to LB retry list with Retry-After support; fix: rate-limit LB playlist fetches to avoid 429 ([8f1c4d2](https://github.com/NyanCod3r/Plex-Track-Manager/commit/8f1c4d222ff5bcf57cd5c6d759d31d7d38987f8d))

## [0.6.0](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.5.0...v0.6.0) (2026-05-03)


### Features

* write per-playlist unmatched JSON files to directory after each playlist ([3c50545](https://github.com/NyanCod3r/Plex-Track-Manager/commit/3c505451165dcea076fd2fc6a55ca297df3a69ab))

## [0.5.0](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.4.5...v0.5.0) (2026-05-03)


### Features

* implement UNMATCHED_TRACKS_JSON -- save tracks with no MBID to file ([925c34e](https://github.com/NyanCod3r/Plex-Track-Manager/commit/925c34e53fe986f52d11ec9642f379efae7e7beb))


### Bug Fixes

* use requests.Session with retry adapter to handle stale LB connections ([55c4d57](https://github.com/NyanCod3r/Plex-Track-Manager/commit/55c4d57ec5e30207c2d70c182a735a105dad3e08))

## [0.4.5](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.4.4...v0.4.5) (2026-05-02)


### Bug Fixes

* serialize MB cache tuple keys as strings; ci: upgrade Node.js 24 actions; fix Dockerfile ENV syntax ([1b59628](https://github.com/NyanCod3r/Plex-Track-Manager/commit/1b59628d9169392e716b265a01a4ef1ab04da705))

## [0.4.4](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.4.3...v0.4.4) (2026-05-02)


### Bug Fixes

* **listenbrainz:** deduplicate by MBID and persist MB lookup cache to disk ([45fc1c5](https://github.com/NyanCod3r/Plex-Track-Manager/commit/45fc1c586f5cb5103a817aac70ff05bab84c362e))

## [Unreleased]

### Bug Fixes

* **listenbrainz:** deduplicate playlist tracks by MusicBrainz MBID to prevent re-adding Spotify-imported tracks on every run

### Features

* **listenbrainz:** persist MusicBrainz MBID lookup cache to disk (`MB_CACHE_FILE`) for faster subsequent sync cycles

## [0.4.3](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.4.2...v0.4.3) (2026-05-02)


### Bug Fixes

* **listenbrainz:** remove duplicate function definitions overriding correct implementations ([433ad81](https://github.com/NyanCod3r/Plex-Track-Manager/commit/433ad8126ca697ed7d2b5b8940355b8779f4c86e))

## [0.4.2](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.4.1...v0.4.2) (2026-05-02)


### Bug Fixes

* **listenbrainz:** exclude Discover Weekly and Release Radar from LB playlist sync ([313756a](https://github.com/NyanCod3r/Plex-Track-Manager/commit/313756a856cfb22cc896d1f24d1c2f5b4f7a81aa))
* **listenbrainz:** log warning when LB token not set instead of silently skipping ([e56dc3e](https://github.com/NyanCod3r/Plex-Track-Manager/commit/e56dc3edf6f3e544a4941ffa04587090c8de6daa))

## [0.4.1](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.4.0...v0.4.1) (2026-05-02)


### Bug Fixes

* **dockerfile:** add missing SYNC_STATE_FILE env var to src/Dockerfile[patch] ([749d489](https://github.com/NyanCod3r/Plex-Track-Manager/commit/749d4898db7c4651da1474428dcd26e292dfea53))

## [0.4.0](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.3.6...v0.4.0) (2026-05-02)


### Features

* **listenbrainz:** integrate ListenBrainz playlist sync into Plex-Track-Manager ([10b2901](https://github.com/NyanCod3r/Plex-Track-Manager/commit/10b2901c08695b1130d7848b361203a7bd19a634))

## [0.3.6](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.3.5...v0.3.6) (2026-04-14)


### Bug Fixes

* **config:** remove hardcoded SYNC_STATE_FILE from Dockerfile, default in Python ([fb0833f](https://github.com/NyanCod3r/Plex-Track-Manager/commit/fb0833fe1b1de6b3a353686e277d228e00306bcd))

## [0.3.5](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.3.4...v0.3.5) (2026-04-14)


### Bug Fixes

* **state:** make sync state file path configurable and persist in /data for Docker ([ae15cc5](https://github.com/NyanCod3r/Plex-Track-Manager/commit/ae15cc5fdaa537ace8a501d0afe31dc46dd0b6ce))

## [0.3.4](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.3.3...v0.3.4) (2026-03-29)


### Bug Fixes

* **scrobble:** query history per music section instead of server-wide to fix 0 scrobbles ([2cf2132](https://github.com/NyanCod3r/Plex-Track-Manager/commit/2cf2132830e57fef2ec35aea6d6cabb046bbd4d3))

## [0.3.3](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.3.2...v0.3.3) (2026-03-29)


### Bug Fixes

* **scrobble:** default SYNC_FULL_HISTORY to true and reset scrobble timestamp ([a7d9866](https://github.com/NyanCod3r/Plex-Track-Manager/commit/a7d9866cd84b6788ea183eaa5b908d2230bf2469))
* **version:** revert manual manifest edit, let release-please manage it automatically ([e5177f8](https://github.com/NyanCod3r/Plex-Track-Manager/commit/e5177f8c2bf38203d948ac2dbb96bd484b879127))
* **version:** sync VERSION in main.py to 0.3.2 matching release-please manifest ([96ba5a9](https://github.com/NyanCod3r/Plex-Track-Manager/commit/96ba5a9ae1ebd321e102901da610531f15a1b0df))

## [0.3.2](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.3.1...v0.3.2) (2026-03-17)


### Bug Fixes

* **logging:** add stage-level INFO summaries for sync, cleanup, and empty playlists ([c9a2f97](https://github.com/NyanCod3r/Plex-Track-Manager/commit/c9a2f97e5ebd86483ffbe271e2f6158dc6cd17c6))

## [0.3.1](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.3.0...v0.3.1) (2026-03-17)


### Bug Fixes

* **logging:** silence pylast internal logger and add descriptive context to debug messages ([296f72a](https://github.com/NyanCod3r/Plex-Track-Manager/commit/296f72ac73a814a70f1ab308bc414e3408f75f50))
* **version:** correct VERSION from 4.0.0 to 0.3.0 ([0f1a7b1](https://github.com/NyanCod3r/Plex-Track-Manager/commit/0f1a7b1360b8f36396691800a1e1835609dc924f))

## [0.2.0](https://github.com/NyanCod3r/Plex-Track-Manager/compare/v0.1.0...v0.2.0) (2026-03-03)


### Features

* **logging:** add emojis, context tags and ASCII banner to all log messages ([e8c508a](https://github.com/NyanCod3r/Plex-Track-Manager/commit/e8c508aa001e5533fb596c486b2ed8f3a78b255f))

## 0.1.0 (2026-03-02)


### Bug Fixes

* **env:** handle empty string env vars in Docker for int/float parsing ([31747aa](https://github.com/NyanCod3r/Plex-Track-Manager/commit/31747aa40f4bb9dfc676ed03460771d78b55c5c4))


### Documentation

* **init:** Initial commit ([57513d7](https://github.com/NyanCod3r/Plex-Track-Manager/commit/57513d756b9bafc9aa30ee091473f81c00236de8))
