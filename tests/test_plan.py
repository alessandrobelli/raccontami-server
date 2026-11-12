import unittest

try:
    from raccontami_sync.narrate import plan_pieces
except ImportError as e:
    # the narration module loads PyTorch; without it (as in the GitHub check) these tests are skipped
    raise unittest.SkipTest(f"narration needs the server's Python environment: {e}")

TOKENS = "Digitized by the Archive . CHAPTER I . Once upon a time .".split()
PARAGRAPHS = [0, 5, 8]


class PlanStartTest(unittest.TestCase):
    def test_everything_is_spoken_without_a_start(self):
        self.assertTrue(all(p["say"] for p in plan_pieces(TOKENS, PARAGRAPHS)))

    def test_pieces_before_the_start_are_silent_and_take_no_time(self):
        first = plan_pieces(TOKENS, PARAGRAPHS, start=5)[0]
        self.assertEqual(("", 0.0), (first["say"], first["pause"]))

    def test_pieces_from_the_start_on_are_spoken(self):
        self.assertTrue(all(p["say"] for p in plan_pieces(TOKENS, PARAGRAPHS, start=5)[1:]))

    def test_token_ranges_do_not_change_with_a_start(self):
        ranges = lambda pieces: [(p["from"], p["to"]) for p in pieces]
        self.assertEqual(ranges(plan_pieces(TOKENS, PARAGRAPHS)), ranges(plan_pieces(TOKENS, PARAGRAPHS, start=5)))

    def test_a_long_paragraph_after_the_start_is_spoken_whole(self):
        # long enough to be split into several pieces
        long = ("Once upon a time there was a piece of wood . " * 80).split()
        tokens = TOKENS[:5] + long
        pieces = plan_pieces(tokens, [0, 5], start=5)
        self.assertGreater(len(pieces), 2)
        self.assertTrue(all(p["say"] for p in pieces[1:]))

    def test_a_silent_token_is_not_spoken(self):
        tokens = ") Once upon a time .".split()
        self.assertNotIn(")", plan_pieces(tokens, [0], silent=[0])[0]["say"])

    def test_a_silent_token_stays_in_its_piece(self):
        tokens = ") Once upon a time .".split()
        self.assertEqual(0, plan_pieces(tokens, [0], silent=[0])[0]["from"])

    def test_a_piece_of_only_silent_tokens_is_silent(self):
        tokens = ") Once upon a time .".split()
        self.assertEqual("", plan_pieces(tokens, [0, 1], silent=[0])[0]["say"])


STORY = "Once upon a time there was a piece of wood .".split()


class PlanVoicesTest(unittest.TestCase):
    # two paragraphs of eleven words: Anna tells the first, Marco the second from its fourth word on
    tokens = STORY + STORY
    narrators = [[0, "Anna"], [14, "Marco"]]

    def plan(self, cast):
        return plan_pieces(self.tokens, [0, 11], narrators=self.narrators, cast=cast)

    def test_each_piece_has_its_narrators_voice(self):
        voices = [p.get("voice") for p in self.plan({"Anna": "a", "Marco": "m"})]
        self.assertEqual(["a", "a", "m"], voices)

    def test_a_change_of_narrator_inside_a_paragraph_cuts_the_piece(self):
        ranges = [(p["from"], p["to"]) for p in self.plan({"Anna": "a", "Marco": "m"})]
        self.assertEqual([(0, 10), (11, 13), (14, 21)], ranges)

    def test_a_narrator_without_a_voice_is_read_by_the_default_one(self):
        voices = [p.get("voice") for p in self.plan({"Marco": "m"})]
        self.assertEqual([None, None, "m"], voices)

    def test_without_a_cast_no_piece_names_a_voice(self):
        self.assertTrue(all("voice" not in p for p in self.plan(None)))

    def test_words_before_the_first_narrator_have_no_voice(self):
        pieces = plan_pieces(self.tokens, [0, 11], narrators=[[11, "Marco"]], cast={"Marco": "m"})
        self.assertEqual([None, "m"], [p.get("voice") for p in pieces])



class VoiceLibraryTest(unittest.TestCase):
    def test_the_clips_in_the_data_folder_are_voices_by_file_name(self):
        import tempfile
        from pathlib import Path

        from raccontami_sync.narrate import voice_library

        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "voices" / "it"
            folder.mkdir(parents=True)
            (folder / "anna.wav").write_bytes(b"")
            (folder / "voices.json").write_text('{"anna": {"label": "Anna", "gender": "f"}}', encoding="utf-8")
            library = voice_library(Path(d), "it")
        self.assertEqual(("Anna", "f"), (library["anna"]["label"], library["anna"]["gender"]))


if __name__ == "__main__":
    unittest.main()
