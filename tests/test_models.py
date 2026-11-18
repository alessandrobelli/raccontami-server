import threading
import time
import unittest
from pathlib import Path

try:
    from raccontami_sync.pipeline import Models, check_whisper_model, scan_corrections
except ModuleNotFoundError as e:
    # the pipeline loads PyTorch; without it (as in the GitHub check) these tests are skipped
    raise unittest.SkipTest(f"the pipeline needs the server's Python environment: {e}")


class OneJobTest(unittest.TestCase):
    def test_jobs_take_turns_on_the_gpu(self):
        models = Models(Path("."), one_job=True)
        spans = []

        def job():
            with models.turn:
                start = time.monotonic()
                time.sleep(0.05)
                spans.append((start, time.monotonic()))

        threads = [threading.Thread(target=job) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        (_, first_end), (second_start, _) = sorted(spans)
        self.assertLessEqual(first_end, second_start)


class WhisperModelTest(unittest.TestCase):
    def test_an_unknown_model_is_refused(self):
        with self.assertRaises(ValueError):
            check_whisper_model("turbbo")


class ScanCorrectionsTest(unittest.TestCase):
    def test_a_language_without_a_word_list_is_synced(self):
        # a language added in the settings may be one wordfreq has no list for
        self.assertEqual([], scan_corrections(["gtattandosi"], ["grattandosi"], [0], [(0, 0)], [True], "xx"))


if __name__ == "__main__":
    unittest.main()
