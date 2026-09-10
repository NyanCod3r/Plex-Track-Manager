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

        self.assertEqual(sanitizeFilename('AC/DC'), "ACDC")
        self.assertEqual(sanitizeFilename('Track: "Live"'), "Track Live")

    def test_empty_input(self):
        from plex_utils import sanitizeFilename

        self.assertEqual(sanitizeFilename(""), "")


class TestWriteAudioMetadata(unittest.TestCase):

    class _FakeAudio(dict):
        def __init__(self):
            super().__init__()
            self.saved = False

        def save(self):
            self.saved = True

    @patch("plex_utils.mutagen.File")
    def test_writes_source_metadata(self, mock_mutagen_file):
        from plex_utils import write_audio_metadata

        fake_audio = self._FakeAudio()
        mock_mutagen_file.return_value = fake_audio

        result = write_audio_metadata("/tmp/Artist - Track.flac", "Artist", "Track", "Album")

        self.assertTrue(result)
        mock_mutagen_file.assert_called_once_with("/tmp/Artist - Track.flac", easy=True)
        self.assertEqual(fake_audio["title"], "Track")
        self.assertEqual(fake_audio["artist"], "Artist")
        self.assertEqual(fake_audio["albumartist"], "Artist")
        self.assertEqual(fake_audio["album"], "Album")
        self.assertTrue(fake_audio.saved)

    @patch("plex_utils.mutagen.File", return_value=None)
    def test_unsupported_file_returns_false(self, mock_mutagen_file):
        from plex_utils import write_audio_metadata

        result = write_audio_metadata("/tmp/x.bin", "Artist", "Track", "")

        self.assertFalse(result)

    def test_empty_metadata_returns_false(self):
        from plex_utils import write_audio_metadata

        result = write_audio_metadata("/tmp/x.flac", "", "", "")

        self.assertFalse(result)

    @patch("plex_utils.mutagen.File")
    def test_normalizes_single_album_and_clears_junk_tags(self, mock_mutagen_file):
        from plex_utils import write_audio_metadata

        fake_audio = self._FakeAudio()
        fake_audio["synopsis"] = ["Official HD Video ..."]
        fake_audio["purl"] = ["https://www.youtube.com/watch?v=x"]
        mock_mutagen_file.return_value = fake_audio

        result = write_audio_metadata("/tmp/x.flac", "Artist", "Track", "Unknown Album")

        self.assertTrue(result)
        self.assertEqual(fake_audio["album"], "Single")
        self.assertNotIn("synopsis", fake_audio)
        self.assertNotIn("purl", fake_audio)
        self.assertTrue(fake_audio.saved)


class TestStripWords(unittest.TestCase):

    def test_strips_junk_words(self):
        from plex_utils import strip_words

        self.assertEqual(
            strip_words("The Buggles - Video Killed The Radio Star (Official Music Video)"),
            "The Buggles - Video Killed The Radio Star",
        )
        self.assertEqual(
            strip_words("Bonnie Tyler - Holding Out for a Hero (Official HD Video)"),
            "Bonnie Tyler - Holding Out for a Hero",
        )

    def test_preserves_clean_text(self):
        from plex_utils import strip_words

        self.assertEqual(strip_words("Holding Out for a Hero"), "Holding Out for a Hero")


class TestNormalizeAlbum(unittest.TestCase):

    def test_maps_missing_and_placeholders_to_single(self):
        from plex_utils import normalize_album

        self.assertEqual(normalize_album(""), "Single")
        self.assertEqual(normalize_album("Unknown Album"), "Single")
        self.assertEqual(normalize_album("UnknownAlbum"), "Single")
        self.assertEqual(normalize_album("[standalone recordings]"), "Single")

    def test_keeps_real_album(self):
        from plex_utils import normalize_album

        self.assertEqual(normalize_album("The Age of Plastic"), "The Age of Plastic")


class TestDownloadValidation(unittest.TestCase):

    def test_youtube_title_score_prefers_matching_title(self):
        from plex_utils import _youtube_title_score

        good = _youtube_title_score("Faces - Statement (Official Video)", "Faces", "Statement")
        bad = _youtube_title_score("Sibiya faces questions about bank transactions", "Faces", "Statement")
        self.assertGreater(good, bad)
        self.assertGreaterEqual(good, 0.7)

    def test_metadata_mismatch_detects_wrong_video(self):
        from plex_utils import _metadata_mismatch

        self.assertTrue(_metadata_mismatch(
            "Newzroom Afrika", "Sibiya faces questions about bank transactions", "Faces", "Statement"))
        self.assertFalse(_metadata_mismatch(
            "FosterThePeople", "Foster The People - Pumped Up Kicks (Official Video)", "Foster The People", "Pumped Up Kicks"))
        self.assertFalse(_metadata_mismatch("", "", "Faces", "Statement"))

    @patch("plex_utils._read_embedded_artist_title", return_value=("Newzroom Afrika", "Sibiya faces questions about bank transactions"))
    def test_download_invalid_on_metadata_mismatch(self, _mock_read):
        from plex_utils import _download_is_valid

        ok, reason = _download_is_valid("/tmp/x.flac", "Faces", "Statement", None)
        self.assertFalse(ok)
        self.assertIn("metadata mismatch", reason)

    @patch("plex_utils._audio_duration", return_value=120.0)
    def test_download_invalid_on_duration_mismatch(self, _mock_dur):
        from plex_utils import _download_is_valid

        ok, reason = _download_is_valid("/tmp/x.flac", "Faces", "Statement", 600.0)
        self.assertFalse(ok)
        self.assertIn("duration mismatch", reason)

    @patch("plex_utils._audio_duration", return_value=280.0)
    @patch("plex_utils._read_embedded_artist_title", return_value=("Faces", "Statement"))
    def test_download_valid_within_duration_tolerance(self, _mock_read, _mock_dur):
        from plex_utils import _download_is_valid

        ok, _ = _download_is_valid("/tmp/x.flac", "Faces", "Statement", 300.0)
        self.assertTrue(ok)

    def test_quarantine_file_moves_file(self):
        import tempfile
        from plex_utils import _quarantine_file

        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, "album")
            q_dir = os.path.join(tmp, "_quarantine")
            os.makedirs(src_dir)
            f = os.path.join(src_dir, "x.flac")
            with open(f, "w") as fh:
                fh.write("x")
            dest = _quarantine_file(f, q_dir, "test")
            self.assertIsNotNone(dest)
            self.assertTrue(os.path.exists(dest))
            self.assertFalse(os.path.exists(f))


class TestStripTrackPrefix(unittest.TestCase):

    def test_strips_disc_track_prefix(self):
        from plex_utils import strip_track_prefix

        self.assertEqual(strip_track_prefix("2-07 Buggles"), "Buggles")
        self.assertEqual(strip_track_prefix("1-10 Lina Santiago"), "Lina Santiago")
        self.assertEqual(strip_track_prefix("08-dan_le_sac"), "dan_le_sac")

    def test_preserves_plain_artists(self):
        from plex_utils import strip_track_prefix

        self.assertEqual(strip_track_prefix("Buggles"), "Buggles")
        self.assertEqual(strip_track_prefix("50 Cent"), "50 Cent")
        self.assertEqual(strip_track_prefix("10cc"), "10cc")


class TestStripTrackPrefixHeuristic(unittest.TestCase):

    def test_strips_number_space_when_known_artist(self):
        import tempfile
        from plex_utils import strip_track_prefix, load_known_artists

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "Cringe.80", "Bran Van 3000"))
            os.makedirs(os.path.join(tmp, "Cringe.80", "Paul Hertzog"))
            load_known_artists(tmp)

            self.assertEqual(strip_track_prefix("01 Bran Van 3000"), "Bran Van 3000")
            self.assertEqual(strip_track_prefix("30 Paul Hertzog"), "Paul Hertzog")
            self.assertEqual(strip_track_prefix("50 Cent"), "50 Cent")
            self.assertEqual(strip_track_prefix("8 Bit Universe"), "8 Bit Universe")
            self.assertEqual(strip_track_prefix("10cc"), "10cc")
            self.assertEqual(strip_track_prefix("2Pac"), "2Pac")
            self.assertEqual(strip_track_prefix("311"), "311")

    def test_dash_prefixes_stripped_without_known_artists(self):
        from plex_utils import strip_track_prefix

        self.assertEqual(strip_track_prefix("2-07 Buggles"), "Buggles")
        self.assertEqual(strip_track_prefix("08-dan_le_sac"), "dan_le_sac")


if __name__ == "__main__":
    unittest.main()