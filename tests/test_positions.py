import tempfile
import unittest
from pathlib import Path

from raccontami_sync.positions import Positions, valid

BOOK = "0123456789abcdef0123456789abcdef"


class PositionsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = Path(self.dir.name) / "positions.json"
        self.positions = Positions(self.file)

    def tearDown(self):
        self.dir.cleanup()

    def test_an_unknown_book_has_no_position(self):
        self.assertIsNone(self.positions.get(BOOK))

    def test_a_position_that_was_put_is_given_back(self):
        self.positions.put(BOOK, 120, 1000, "phone", "Phone")
        self.assertEqual(120, self.positions.get(BOOK)["token"])

    def test_a_newer_position_replaces_the_older(self):
        self.positions.put(BOOK, 120, 1000, "phone")
        self.positions.put(BOOK, 300, 2000, "tablet")
        self.assertEqual("tablet", self.positions.get(BOOK)["device"])

    def test_an_older_position_does_not_replace_the_newer(self):
        self.positions.put(BOOK, 300, 2000, "tablet")
        self.positions.put(BOOK, 120, 1000, "phone")
        self.assertEqual(300, self.positions.get(BOOK)["token"])

    def test_putting_an_older_position_answers_with_the_newer(self):
        self.positions.put(BOOK, 300, 2000, "tablet")
        self.assertEqual(300, self.positions.put(BOOK, 120, 1000, "phone")["token"])

    def test_positions_are_still_there_after_a_restart(self):
        self.positions.put(BOOK, 120, 1000, "phone")
        self.assertEqual(120, Positions(self.file).get(BOOK)["token"])

    def test_a_damaged_file_counts_as_empty(self):
        self.file.write_text("{not json", encoding="utf-8")
        self.assertIsNone(Positions(self.file).get(BOOK))


class ValidTest(unittest.TestCase):
    def test_a_well_formed_position_is_accepted(self):
        self.assertEqual((5, 1000, "phone", "Phone"), valid(BOOK, {"token": 5, "at": 1000, "device": "phone", "name": "Phone"}))

    def test_a_key_that_is_not_a_hash_is_refused(self):
        self.assertIsNone(valid("../../etc", {"token": 5, "at": 1000, "device": "phone"}))

    def test_a_negative_word_is_refused(self):
        self.assertIsNone(valid(BOOK, {"token": -1, "at": 1000, "device": "phone"}))

    def test_a_position_without_a_device_is_refused(self):
        self.assertIsNone(valid(BOOK, {"token": 5, "at": 1000}))

    def test_true_is_not_a_number(self):
        self.assertIsNone(valid(BOOK, {"token": True, "at": 1000, "device": "phone"}))


if __name__ == "__main__":
    unittest.main()
