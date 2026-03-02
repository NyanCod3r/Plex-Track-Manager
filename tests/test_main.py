from unittest.mock import patch, MagicMock, PropertyMock
import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestGetLastfmNetwork(unittest.TestCase):

    @patch("lastfm_utils.pylast.LastFMNetwork")
    @patch("lastfm_utils.pylast.md5", return_value="hashed_pw")
    def test_returns_network_on_success(self, mock_md5, mock_lfm):
        mock_network = MagicMock()
        mock_lfm.return_value = mock_network

        from lastfm_utils import get_lastfm_network

        result = get_lastfm_network("key", "secret", "user", "pass")
        self.assertEqual(result, mock_network)
        mock_md5.assert_called_once_with("pass")
        mock_lfm.assert_called_once_with(
            api_key="key",
            api_secret="secret",
            username="user",
            password_hash="hashed_pw",
        )

    @patch("lastfm_utils.pylast.LastFMNetwork", side_effect=Exception("auth fail"))
    @patch("lastfm_utils.pylast.md5", return_value="hashed_pw")
    def test_returns_none_on_failure(self, mock_md5, mock_lfm):
        from lastfm_utils import get_lastfm_network

        result = get_lastfm_network("key", "secret", "user", "pass")
        self.assertIsNone(result)


class TestProcessOneStarDeletions(unittest.TestCase):

    @patch("main.delete_plex_track")
    @patch("main.get_one_star_tracks")
    def test_deletes_one_star_tracks(self, mock_get, mock_delete):
        mock_section = MagicMock()
        mock_section.type = "artist"
        mock_section.title = "Music"

        mock_plex = MagicMock()
        mock_plex.library.sections.return_value = [mock_section]

        mock_track = MagicMock()
        mock_get.return_value = [{"plex_track": mock_track}]

        from main import process_one_star_deletions

        process_one_star_deletions(mock_plex)

        mock_get.assert_called_once_with(mock_plex, "Music")
        mock_delete.assert_called_once_with(mock_track, "Music")

    @patch("main.get_one_star_tracks", return_value=[])
    def test_no_tracks_does_nothing(self, mock_get):
        mock_section = MagicMock()
        mock_section.type = "artist"
        mock_section.title = "Music"

        mock_plex = MagicMock()
        mock_plex.library.sections.return_value = [mock_section]

        from main import process_one_star_deletions

        process_one_star_deletions(mock_plex)
        mock_get.assert_called_once()


class TestEnsureLocalFiles(unittest.TestCase):

    @patch("plex_utils.track_exists_in_directory", return_value=True)
    @patch("plex_utils.createFolder")
    def test_skips_existing_track(self, mock_folder, mock_exists):
        from plex_utils import ensure_local_files

        tracks = [{"title": "Track A", "artist": "Artist A", "album": "Album A"}]
        ensure_local_files(tracks, "Discover Weekly", "/tmp/music")

        mock_folder.assert_called_once()
        mock_exists.assert_called_once()

    @patch("plex_utils.download_track")
    @patch("plex_utils.find_and_rename_track_by_tag", return_value=False)
    @patch("plex_utils.track_exists_in_directory", return_value=False)
    @patch("plex_utils.createFolder")
    def test_queues_download_for_missing(self, mock_folder, mock_exists, mock_rename, mock_dl):
        from plex_utils import ensure_local_files

        tracks = [{"title": "Track B", "artist": "Artist B", "album": "Album B"}]
        ensure_local_files(tracks, "Release Radar", "/tmp/music")

        mock_dl.assert_called_once()


class TestSanitizeFilename(unittest.TestCase):

    def test_removes_special_characters(self):
        from plex_utils import sanitizeFilename

        self.assertEqual(sanitizeFilename('AC/DC'), "AC_DC")
        self.assertEqual(sanitizeFilename('Track: "Live"'), "Track_ _Live_")

    def test_empty_input(self):
        from plex_utils import sanitizeFilename

        self.assertEqual(sanitizeFilename(""), "")


if __name__ == "__main__":
    unittest.main()