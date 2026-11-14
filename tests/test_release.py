"""Run from the repository root with:  python -m unittest discover tests"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from raccontami_sync import connect_window, serve, version
from raccontami_sync.tls import digit_code, short_code


class DigitCodeTest(unittest.TestCase):
    def test_the_code_is_twenty_digits_in_groups_of_four(self):
        self.assertEqual("0000 0000 0000 0000 0001", digit_code("0000000000000001" + "f" * 48))

    def test_the_largest_start_of_a_fingerprint_still_fits(self):
        self.assertEqual("1844 6744 0737 0955 1615", digit_code("f" * 64))

    def test_it_is_the_same_number_as_the_older_code(self):
        mark = "3fa907c2b1d488e0" + "0" * 48
        self.assertEqual(int(short_code(mark).replace("-", ""), 16), int(digit_code(mark).replace(" ", "")))

    def test_the_older_form_is_said_next_to_the_digits_for_an_app_not_yet_updated(self):
        rows = connect_window.facts("https://x:8765", "abc", "token.txt", "0000 0000 0000 0000 0001", "0000-0000-0000-0001")
        self.assertIn("0000-0000-0000-0001", rows[2][2])


class VersionTest(unittest.TestCase):
    def test_the_version_is_the_one_in_the_file_at_the_top_of_the_repository(self):
        written = json.loads(version.FILE.read_text(encoding="utf-8"))["version"]
        self.assertEqual(written, version.VERSION)

    def test_it_is_numbers_with_dots_so_that_the_page_can_compare_it(self):
        self.assertRegex(version.VERSION, r"^\d+(\.\d+)+$")

    def test_a_copy_without_the_file_still_gives_a_version(self):
        self.assertEqual("0", version.read(Path(tempfile.mkdtemp()) / "version.json"))


class OwnToolsTest(unittest.TestCase):
    def test_the_ffmpeg_the_setup_brought_comes_first(self):
        home = Path(tempfile.mkdtemp())
        (home / "tools" / "ffmpeg" / "bin").mkdir(parents=True)
        env = {"RACCONTAMI_HOME": str(home), "PATH": "elsewhere"}
        serve.use_own_tools(env)
        self.assertEqual([str(home / "tools" / "ffmpeg" / "bin"), "elsewhere"], env["PATH"].split(os.pathsep))

    def test_without_it_the_path_is_left_alone(self):
        env = {"RACCONTAMI_HOME": tempfile.mkdtemp(), "PATH": "elsewhere"}
        serve.use_own_tools(env)
        self.assertEqual("elsewhere", env["PATH"])


if __name__ == "__main__":
    unittest.main()
