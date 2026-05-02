# Changelog

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
