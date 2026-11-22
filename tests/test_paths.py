"""Run from the repository root with:  python -m unittest discover tests"""

import unittest
from pathlib import Path

from raccontami_sync import paths

MODELS = Path("E:/raccontami-models")


class ModelHomesTest(unittest.TestCase):
    def test_a_chosen_models_folder_wins_over_a_hf_home_set_on_the_computer(self):
        env = {"RACCONTAMI_MODELS": str(MODELS), "HF_HOME": "F:/cache/huggingface"}
        self.assertEqual(str(MODELS / "hf"), paths.model_homes(env, MODELS)["HF_HOME"])

    def test_a_chosen_models_folder_wins_over_a_torch_home_set_on_the_computer(self):
        env = {"RACCONTAMI_MODELS": str(MODELS), "TORCH_HOME": "F:/cache/torch"}
        self.assertEqual(str(MODELS / "torch"), paths.model_homes(env, MODELS)["TORCH_HOME"])

    def test_without_a_chosen_folder_a_hf_home_set_on_the_computer_is_kept(self):
        env = {"HF_HOME": "F:/cache/huggingface"}
        self.assertEqual("F:/cache/huggingface", paths.model_homes(env, MODELS)["HF_HOME"])

    def test_without_either_the_models_go_in_the_models_folder(self):
        self.assertEqual(str(MODELS / "hf"), paths.model_homes({}, MODELS)["HF_HOME"])

    def test_an_empty_choice_is_no_choice(self):
        env = {"RACCONTAMI_MODELS": "", "HF_HOME": "F:/cache/huggingface"}
        self.assertEqual("F:/cache/huggingface", paths.model_homes(env, MODELS)["HF_HOME"])


if __name__ == "__main__":
    unittest.main()
