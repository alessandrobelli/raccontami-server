"""Run from the repository root with:  python -m unittest discover tests"""

import json
import tempfile
import unittest
from pathlib import Path

from raccontami_sync import aligners

LETTERS = {"<pad>": 0, "<s>": 1, "</s>": 2, "<unk>": 3, "|": 4, **{c: 5 + i for i, c in enumerate("abcdefghij'")}}
CTC = {"architectures": ["Wav2Vec2ForCTC"]}


class AlignModelsTest(unittest.TestCase):
    def test_without_settings_english_and_italian_are_there(self):
        self.assertEqual(aligners.DEFAULTS, aligners.align_models({}))

    def test_a_setting_adds_a_language(self):
        found = aligners.align_models({"RACCONTAMI_ALIGN_MODEL_FR": "someone/french"})
        self.assertEqual("someone/french", found["fr"])

    def test_a_setting_changes_a_language(self):
        found = aligners.align_models({"RACCONTAMI_ALIGN_MODEL_EN": "someone/english"})
        self.assertEqual("someone/english", found["en"])

    def test_spaces_around_the_value_are_dropped(self):
        found = aligners.align_models({"RACCONTAMI_ALIGN_MODEL_DE": "  someone/german "})
        self.assertEqual("someone/german", found["de"])

    def test_an_empty_value_changes_nothing(self):
        self.assertEqual(aligners.DEFAULTS, aligners.align_models({"RACCONTAMI_ALIGN_MODEL_EN": " "}))

    def test_other_settings_are_not_taken(self):
        self.assertEqual(aligners.DEFAULTS, aligners.align_models({"RACCONTAMI_WHISPER_MODEL": "turbo"}))


class RefusalTest(unittest.TestCase):
    def test_a_ctc_model_that_writes_letters_is_taken(self):
        self.assertIsNone(aligners.refusal(CTC, LETTERS))

    def test_a_model_without_architectures_is_taken(self):
        self.assertIsNone(aligners.refusal({}, LETTERS))

    def test_a_model_of_another_kind_is_refused(self):
        self.assertIn("not a CTC", aligners.refusal({"architectures": ["WhisperForConditionalGeneration"]}, LETTERS))

    def test_a_model_without_a_vocab_is_refused(self):
        self.assertIn("vocab.json", aligners.refusal(CTC, None))

    def test_a_model_that_writes_word_pieces_is_refused(self):
        pieces = {f"piece{i}": i for i in range(50)}
        self.assertIn("word pieces", aligners.refusal(CTC, pieces))

    def test_a_vocab_of_a_model_per_language_is_refused(self):
        self.assertIn("vocab.json", aligners.refusal(CTC, {"fra": LETTERS}))


class ReadFilesTest(unittest.TestCase):
    def test_a_model_folder_is_read_without_the_network(self):
        d = Path(tempfile.mkdtemp())
        (d / "config.json").write_text(json.dumps(CTC), encoding="utf-8")
        (d / "vocab.json").write_text(json.dumps(LETTERS), encoding="utf-8")
        self.assertEqual((CTC, LETTERS), aligners.read_files(str(d)))

    def test_a_folder_without_a_vocab_gives_none_for_it(self):
        d = Path(tempfile.mkdtemp())
        (d / "config.json").write_text(json.dumps(CTC), encoding="utf-8")
        self.assertIsNone(aligners.read_files(str(d))[1])


class CheckTest(unittest.TestCase):
    def test_the_models_that_come_with_the_server_are_not_checked(self):
        aligners.check(aligners.DEFAULTS, languages=set(), log=self.fail)  # no lookup, no message

    def test_a_language_whisper_does_not_know_stops_the_start(self):
        with self.assertRaises(ValueError):
            aligners.check({"xx": "someone/model"}, languages={"en", "it"})

    def test_a_folder_with_a_model_of_another_kind_stops_the_start(self):
        d = Path(tempfile.mkdtemp())
        (d / "config.json").write_text(json.dumps({"architectures": ["BertModel"]}), encoding="utf-8")
        (d / "vocab.json").write_text(json.dumps(LETTERS), encoding="utf-8")
        with self.assertRaises(ValueError):
            aligners.check({"fr": str(d)}, languages={"fr"})


if __name__ == "__main__":
    unittest.main()
