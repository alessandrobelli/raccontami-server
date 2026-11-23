"""Run from the repository root with:  python -m unittest discover tests"""

import tempfile
import unittest
from pathlib import Path

from raccontami_sync import langmanage, settings


class Setup:
    """A home folder with a models folder, a word-timing model and a made narrator, as an install leaves them."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.models, self.data, self.tts = root / "models", root / "server-data", root / "tts"
        self.hub = self.models / "hf" / "hub"
        for repo in ("mpoyraz/wav2vec2-xls-r-300m-cv7-turkish", "openbmb/VoxCPM2", "facebook/wav2vec2-large-960h-lv60-self"):
            d = langmanage.repo_dir(self.hub, repo)
            d.mkdir(parents=True)
            (d / "weights.bin").write_bytes(b"x" * 1000)
        (self.data / "narrators").mkdir(parents=True)
        (self.data / "narrators" / "voxcpm2_tr_ref.wav").write_bytes(b"y" * 100)
        for env in ("env-a", "env-c"):
            (self.tts / env).mkdir(parents=True)

    def plan(self, code, enabled, installed=("qwen3", "voxcpm2")):
        return langmanage.remove_plan(code, enabled, set(installed), self.hub, self.models, self.data, self.tts,
                                      samples={"it", "tr"})


class RemovePlanTest(unittest.TestCase):
    def setUp(self):
        self.s = Setup()
        self.addCleanup(self.s.tmp.cleanup)

    def test_the_language_leaves_the_list(self):
        self.assertEqual(["en"], self.s.plan("tr", ["en", "tr"])["languages"])

    def test_its_word_timing_model_and_narrator_are_deleted(self):
        delete = self.s.plan("tr", ["en", "tr"])["delete"]
        self.assertEqual({langmanage.repo_dir(self.s.hub, "mpoyraz/wav2vec2-xls-r-300m-cv7-turkish"),
                          self.s.data / "narrators" / "voxcpm2_tr_ref.wav"}, set(delete))

    def test_a_voice_no_other_language_needs_is_offered(self):
        self.assertEqual(["voxcpm2"], list(self.s.plan("tr", ["en", "tr"])["unusedVoices"]))

    def test_a_voice_still_needed_is_not_offered(self):
        self.assertEqual({}, self.s.plan("tr", ["en", "it", "tr"])["unusedVoices"])

    def test_the_unused_voice_brings_its_environment_and_model(self):
        paths = self.s.plan("tr", ["en", "tr"])["unusedVoices"]["voxcpm2"]["delete"]
        self.assertEqual({self.s.tts / "env-a", langmanage.repo_dir(self.s.hub, "openbmb/VoxCPM2")}, set(paths))

    def test_the_space_freed_is_counted(self):
        self.assertEqual(1100, self.s.plan("tr", ["en", "tr"])["bytes"])

    def test_models_in_a_shared_cache_are_kept(self):
        shared = Path(self.s.tmp.name) / "shared-hf" / "hub"
        plan = langmanage.remove_plan("tr", ["en", "tr"], {"voxcpm2"}, shared, self.s.models, self.s.data, self.s.tts, samples={"tr"})
        self.assertEqual([self.s.data / "narrators" / "voxcpm2_tr_ref.wav"], plan["delete"])

    def test_the_last_language_cannot_be_removed(self):
        self.assertIsNotNone(self.s.plan("en", ["en"])["refused"])


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.s = Setup()
        self.addCleanup(self.s.tmp.cleanup)

    def status(self, enabled, installed=("qwen3", "voxcpm2")):
        rows = langmanage.status(enabled, set(installed), self.s.hub, self.s.models, self.s.data, samples={"it", "tr"})
        return {r["code"]: r for r in rows}

    def test_every_language_of_the_catalogue_is_listed(self):
        from raccontami_sync import languages
        self.assertEqual(set(languages.LANGUAGES), set(self.status(["en"])))

    def test_an_installed_language_says_so(self):
        self.assertTrue(self.status(["en", "tr"])["tr"]["installed"])

    def test_a_language_whose_voice_is_installed_can_be_added_here(self):
        self.assertEqual("here", self.status(["en"])["es"]["add"])

    def test_a_language_needing_a_voice_not_installed_needs_the_installer(self):
        self.assertEqual("installer", self.status(["en"], installed=("qwen3",))["tr"]["add"])

    def test_the_space_a_language_takes_is_given(self):
        self.assertEqual(1100, self.status(["en", "tr"])["tr"]["bytes"])


class SetLineTest(unittest.TestCase):
    def test_a_line_is_added_with_its_note(self):
        self.assertEqual({"RACCONTAMI_X": "1"}, settings.parse(settings.set_line("# mine\n", "RACCONTAMI_X", "1", "# note")))

    def test_a_line_is_replaced_where_it_is(self):
        text = settings.set_line("A=1\nRACCONTAMI_X=0\nRACCONTAMI_Y=2\n", "RACCONTAMI_X", "1", "# note")
        self.assertEqual("A=1\nRACCONTAMI_X=1\nRACCONTAMI_Y=2\n", text)


if __name__ == "__main__":
    unittest.main()
