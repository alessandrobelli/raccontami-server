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


if __name__ == "__main__":
    unittest.main()
