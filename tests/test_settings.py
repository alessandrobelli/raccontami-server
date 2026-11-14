"""Run from the repository root with:  python -m unittest discover tests"""

import tempfile
import unittest
from pathlib import Path

from raccontami_sync import awake, settings


class ParseTest(unittest.TestCase):
    def test_a_setting_is_read(self):
        self.assertEqual({"RACCONTAMI_ONE_JOB": "1"}, settings.parse("RACCONTAMI_ONE_JOB=1\n"))

    def test_notes_and_empty_lines_are_skipped(self):
        self.assertEqual({}, settings.parse("# RACCONTAMI_TLS=0\n\n   \n"))

    def test_spaces_and_quotes_around_a_value_are_dropped(self):
        self.assertEqual({"RACCONTAMI_NAME": "Studio PC"}, settings.parse(' RACCONTAMI_NAME = "Studio PC" '))

    def test_other_names_are_not_taken(self):
        self.assertEqual({}, settings.parse("PATH=C:\\somewhere\n"))

    def test_a_value_may_contain_an_equals_sign(self):
        self.assertEqual({"RACCONTAMI_TOKEN": "a=b"}, settings.parse("RACCONTAMI_TOKEN=a=b"))


class LoadTest(unittest.TestCase):
    def home(self, text):
        d = Path(tempfile.mkdtemp())
        (d / settings.FILE).write_text(text, encoding="utf-8")
        return str(d)

    def test_the_file_in_the_home_folder_is_applied(self):
        env = {"RACCONTAMI_HOME": self.home("RACCONTAMI_TLS=0\n")}
        settings.load(env)
        self.assertEqual("0", env["RACCONTAMI_TLS"])

    def test_what_the_start_already_set_wins(self):
        env = {"RACCONTAMI_HOME": self.home("RACCONTAMI_PORT=9000\n"), "RACCONTAMI_PORT": "8765"}
        settings.load(env)
        self.assertEqual("8765", env["RACCONTAMI_PORT"])

    def test_the_file_cannot_move_the_home_folder_it_was_found_in(self):
        home = self.home("RACCONTAMI_HOME=C:\\elsewhere\n")
        env = {"RACCONTAMI_HOME": home}
        settings.load(env)
        self.assertEqual(home, env["RACCONTAMI_HOME"])

    def test_without_a_file_nothing_changes(self):
        env = {"RACCONTAMI_HOME": tempfile.mkdtemp()}
        self.assertEqual([], settings.load(env))

    def test_a_file_saved_by_notepad_with_a_mark_at_its_start_is_read(self):
        d = Path(tempfile.mkdtemp())
        (d / settings.FILE).write_bytes(b"\xef\xbb\xbfRACCONTAMI_ONE_JOB=1\r\n")
        env = {"RACCONTAMI_HOME": str(d)}
        settings.load(env)
        self.assertEqual("1", env["RACCONTAMI_ONE_JOB"])


class AwakeTest(unittest.TestCase):
    def test_wanted_on_windows(self):
        self.assertTrue(awake.wanted("win32", {}))

    def test_not_wanted_when_switched_off(self):
        self.assertFalse(awake.wanted("win32", {"RACCONTAMI_KEEP_AWAKE": "0"}))

    def test_not_wanted_elsewhere(self):
        self.assertFalse(awake.wanted("linux", {}))


if __name__ == "__main__":
    unittest.main()
