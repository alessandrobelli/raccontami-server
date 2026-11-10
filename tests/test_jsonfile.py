"""Run from the repository root with:  python -m unittest discover tests"""

import tempfile
import unittest
from pathlib import Path

from raccontami_sync.jsonfile import read_json, write_json


class JsonFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.file = self.dir / "status.json"

    def test_what_is_written_is_read_back(self):
        write_json(self.file, {"state": "running", "progress": 0.4})
        self.assertEqual({"state": "running", "progress": 0.4}, read_json(self.file))

    def test_writing_leaves_no_temporary_file(self):
        write_json(self.file, {"state": "done"})
        self.assertEqual(["status.json"], [f.name for f in self.dir.iterdir()])

    def test_a_missing_file_reads_as_none(self):
        self.assertIsNone(read_json(self.file))

    def test_an_empty_file_reads_as_none(self):
        self.file.write_text("", encoding="utf-8")
        self.assertIsNone(read_json(self.file))

    def test_a_file_cut_short_reads_as_none(self):
        self.file.write_text('{"state": "runn', encoding="utf-8")
        self.assertIsNone(read_json(self.file))


if __name__ == "__main__":
    unittest.main()
