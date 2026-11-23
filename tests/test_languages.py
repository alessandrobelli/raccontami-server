"""Run from the repository root with:  python -m unittest discover tests"""

import unittest
from pathlib import Path

from raccontami_sync import aligners, languages

# the words app 0.1.5 takes for an unreachable server (tests/test_unfinished.py, ForPhoneTest)
APP_UNREACHABLE_MARKS = ("refused", "timeout", "timed out", "unreachable", "failed to connect", "unable to resolve",
                         "connection", "network")


class CatalogueTest(unittest.TestCase):
    def test_every_language_has_a_word_timing_model(self):
        self.assertEqual([], [k for k, v in languages.LANGUAGES.items() if not v["aligner"]])

    def test_every_voice_named_by_a_language_exists(self):
        named = {e for v in languages.LANGUAGES.values() for e in v["voices"]}
        self.assertEqual(set(), named - set(languages.VOICE_MODELS))

    def test_a_qwen_language_has_its_name_for_qwen(self):
        missing = [k for k, v in languages.LANGUAGES.items() if "qwen3" in v["voices"] and not v.get("qwen")]
        self.assertEqual([], missing)

    def test_without_a_setting_the_server_has_english_and_italian_as_before(self):
        self.assertEqual(["en", "it"], languages.enabled({}))

    def test_the_setting_chooses_the_languages(self):
        self.assertEqual(["en", "es", "tr"], languages.enabled({"RACCONTAMI_LANGUAGES": "tr, es,en"}))

    def test_an_unknown_language_in_the_setting_is_left_out(self):
        self.assertEqual(["en"], languages.enabled({"RACCONTAMI_LANGUAGES": "en,xx"}))


class VoiceChoiceTest(unittest.TestCase):
    def test_italian_keeps_its_tested_voice(self):
        self.assertEqual("voxcpm2", languages.voice_for("it", {"voxcpm2", "qwen3"}))

    def test_italian_falls_back_to_qwen_without_voxcpm2(self):
        self.assertEqual("qwen3", languages.voice_for("it", {"qwen3"}))

    def test_a_language_without_an_installed_voice_has_none(self):
        self.assertIsNone(languages.voice_for("es", {"voxcpm2"}))

    def test_voxcpm2_needs_a_narrator_sample_for_the_language(self):
        self.assertIsNone(languages.voice_for("tr", {"voxcpm2", "qwen3"}, samples=set()))

    def test_english_and_italian_need_both_voices_as_today(self):
        self.assertEqual({"qwen3", "voxcpm2"}, languages.voices_needed(["en", "it"]))

    def test_english_alone_needs_only_qwen(self):
        self.assertEqual({"qwen3"}, languages.voices_needed(["en"]))

    def test_the_voice_config_tells_qwen_the_language(self):
        cfg = languages.voice_config("es", "qwen3", python="py.exe")
        self.assertEqual(("qwen3", "Spanish"), (cfg["engine"], cfg["language"]))


class MadeNarratorTest(unittest.TestCase):
    def test_turkish_will_get_a_narrator_made_by_voxcpm2(self):
        self.assertEqual({"voxcpm2"}, languages.voices_needed(["tr"], samples=set()))

    def test_the_languages_whose_narrator_is_made_on_this_computer(self):
        self.assertEqual(["tr"], languages.narrators_to_make(["en", "it", "tr"], samples={"it"}))

    def test_a_made_narrator_is_found_in_the_data_folder(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "narrators").mkdir()
            (Path(d) / "narrators" / "voxcpm2_tr_ref.wav").write_bytes(b"RIFF")
            self.assertIn("tr", languages.samples(Path(d)))

    def test_a_made_narrator_is_used_once_it_exists(self):
        self.assertEqual("voxcpm2", languages.voice_for("tr", {"voxcpm2"}, samples={"tr"}))

    def test_every_language_has_a_sample_text_for_its_narrator(self):
        self.assertEqual(set(), set(languages.LANGUAGES) - set(languages.SAMPLE_TEXT))


class VoiceTableTest(unittest.TestCase):
    def table(self, langs, installed):
        return languages.voice_table(langs, installed, python_of=lambda v: f"{v}.exe", samples={"it"})

    def test_only_languages_with_an_installed_voice_can_be_narrated(self):
        self.assertEqual(["en"], sorted(self.table(["en", "it"], {"qwen3"}).keys() - {"it"}))

    def test_english_and_italian_get_todays_voices(self):
        t = self.table(["en", "it"], {"qwen3", "voxcpm2"})
        self.assertEqual(("qwen3", "voxcpm2"), (t["en"]["engine"], t["it"]["engine"]))

    def test_without_voices_nothing_is_narrated(self):
        self.assertEqual({}, self.table(["en", "es"], set()))

    def test_turkish_without_a_narrator_sample_is_not_narrated(self):
        self.assertNotIn("tr", self.table(["tr"], {"qwen3", "voxcpm2"}))

    def test_a_made_narrator_is_cloned_from_the_data_folder(self):
        t = languages.voice_table(["tr"], {"voxcpm2"}, python_of=lambda v: "py", samples={"tr"}, data=Path("D:/data"))
        self.assertEqual(str(Path("D:/data") / "narrators" / "voxcpm2_tr_ref.wav"), t["tr"]["voice"])


class MissingLanguageTest(unittest.TestCase):
    def test_a_language_without_a_voice_is_said_so(self):
        self.assertIn("Turkish", languages.no_voice("tr"))

    def test_no_voice_avoids_the_words_app_0_1_5_takes_for_an_unreachable_server(self):
        said = languages.no_voice("tr").lower()
        self.assertEqual([], [m for m in APP_UNREACHABLE_MARKS if m in said])

    def test_the_phone_is_told_in_plain_words_which_language_is_missing(self):
        self.assertIn("Spanish", languages.missing("es"))

    def test_it_avoids_the_words_app_0_1_5_takes_for_an_unreachable_server(self):
        said = (languages.missing("es") + languages.missing("xx")).lower()
        self.assertEqual([], [m for m in APP_UNREACHABLE_MARKS if m in said])


class DownloadsTest(unittest.TestCase):
    def test_english_and_italian_download_todays_four_models(self):
        self.assertEqual({"facebook/wav2vec2-large-960h-lv60-self", "jonatasgrosman/wav2vec2-large-xlsr-53-italian",
                          "openbmb/VoxCPM2", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"},
                         set(languages.downloads(["en", "it"], samples={"it"})))

    def test_spanish_alone_downloads_its_word_timing_model_and_qwen(self):
        self.assertEqual({"jonatasgrosman/wav2vec2-large-xlsr-53-spanish", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"},
                         set(languages.downloads(["es"], samples={"it"})))


class SizesTest(unittest.TestCase):
    def test_more_languages_never_cost_less(self):
        self.assertLess(languages.size_gb(["en"]), languages.size_gb(["en", "it"]))


class LettersTest(unittest.TestCase):
    VOCAB = {"|": 0, "s": 1, "t": 2, "r": 3, "a": 4, "e": 5, "c": 6, "o": 7, "u": 8}

    def test_a_letter_is_taken_as_written(self):
        self.assertEqual([1, 2], aligners.letter_ids("st", self.VOCAB))

    def test_an_accent_the_model_lacks_falls_back_to_the_plain_letter(self):
        self.assertEqual([6, 7], aligners.letter_ids("ço", self.VOCAB))

    def test_german_sharp_s_becomes_ss_when_the_model_has_no_sharp_s(self):
        self.assertEqual([1, 2, 3, 4, 1, 1, 5], aligners.letter_ids("straße", self.VOCAB))

    def test_a_letter_with_no_match_is_left_out(self):
        self.assertEqual([4], aligners.letter_ids("a中", self.VOCAB))


if __name__ == "__main__":
    unittest.main()
