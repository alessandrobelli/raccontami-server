"""Run from the repository root with:  python -m unittest discover tests"""

import unittest

from raccontami_sync.textnorm import norm_parts


class NormPartsTest(unittest.TestCase):
    def test_hindi_keeps_its_vowel_signs(self):
        self.assertEqual(["हिंदी"], norm_parts("हिंदी", "hi"))

    def test_italian_apostrophes_split_words(self):
        self.assertEqual(["l", "amico"], norm_parts("l'amico", "it"))

    def test_french_apostrophes_split_words_too(self):
        self.assertEqual(["l", "homme"], norm_parts("l'homme", "fr"))

    def test_english_apostrophes_are_dropped(self):
        self.assertEqual(["dont"], norm_parts("don't", "en"))

    def test_punctuation_is_dropped(self):
        self.assertEqual(["hola"], norm_parts("¡Hola!", "es"))

    def test_accented_letters_stay_one_letter(self):
        self.assertEqual(["café"], norm_parts("Café", "fr"))


if __name__ == "__main__":
    unittest.main()
