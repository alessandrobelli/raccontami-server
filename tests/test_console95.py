"""Run from the repository root with:  python -m unittest discover tests

The installer's setup window (raccontami_sync/console95.py): what it reads in a step's output, and that every
line it draws fits the console."""

import unittest
from pathlib import Path

from raccontami_sync import console95

TORCH_URL = "https://download-r2.pytorch.org/whl/cu128/torch-2.11.0%2Bcu128-cp312-cp312-win_amd64.whl (2.9 GB)"


class ReadTest(unittest.TestCase):
    def test_pip_raw_progress_is_a_fraction(self):
        self.assertEqual(0.25, console95.read("Progress 250 of 1000").fraction)

    def test_pip_raw_progress_is_not_logged(self):
        self.assertFalse(console95.read("Progress 250 of 1000").log)

    def test_a_download_names_the_package_and_its_size(self):
        self.assertEqual("Downloading torch 2.11.0+cu128 (2.9 GB)", console95.read("Downloading " + TORCH_URL).detail)

    def test_a_download_starts_its_bar_at_zero(self):
        self.assertEqual(0.0, console95.read("Downloading " + TORCH_URL).fraction)

    def test_metadata_lines_are_not_shown(self):
        self.assertIsNone(console95.read("  Downloading sympy-1.14.0-py3-none-any.whl.metadata (12 kB)"))

    def test_collecting_names_the_package_without_its_version_rule(self):
        self.assertEqual("Looking up sympy", console95.read("Collecting sympy>=1.13.3 (from torch==2.11.0)").detail)

    def test_installing_counts_the_packages(self):
        self.assertEqual("Installing 3 packages (this takes a while)",
                         console95.read("Installing collected packages: mpmath, sympy, torch").detail)

    def test_installing_has_no_known_end(self):
        self.assertIsNone(console95.read("Installing collected packages: mpmath, sympy, torch").fraction)

    def test_a_tqdm_bar_is_a_fraction(self):
        self.assertEqual(0.6, console95.read("Fetching 10 files:  60%|██████    | 6/10 [00:00<00:00, 21.13it/s]").fraction)

    def test_a_tqdm_bar_keeps_its_description(self):
        self.assertEqual("Fetching 10 files", console95.read("Fetching 10 files:  60%|██████    | 6/10 [00:00<00:00]").detail)

    def test_an_unfinished_tqdm_bar_is_not_logged(self):
        self.assertFalse(console95.read("Fetching 10 files:  60%|██████    | 6/10 [00:00<00:00]").log)

    def test_a_finished_tqdm_bar_is_logged(self):
        self.assertTrue(console95.read("Fetching 10 files: 100%|██████████| 10/10 [00:01<00:00]").log)

    def test_the_model_download_says_which_model(self):
        self.assertEqual("Model 2 of 5: facebook/wav2vec2-base-960h",
                         console95.read("model 2 of 5: facebook/wav2vec2-base-960h").detail)

    def test_an_unknown_line_is_only_logged(self):
        self.assertIsNone(console95.read("UserWarning: something about symlinks"))

    def test_colours_in_a_line_are_ignored(self):
        self.assertEqual(0.5, console95.read("\x1b[32mProgress 1 of 2\x1b[0m").fraction)

    def test_text_glued_after_a_tqdm_bar_is_kept_for_the_log(self):  # a warning printed on the bar's line
        line = "Fetching 10 files:   0%|          | 0/10 [00:00<?, ?it/s]UserWarning: no symlinks"
        self.assertEqual("UserWarning: no symlinks", console95.read(line).extra)


class SplitTest(unittest.TestCase):
    def test_carriage_returns_and_newlines_both_end_a_line(self):
        self.assertEqual((["a", "b", "c"], b"d"), console95.split_lines(b"a\rb\r\nc\nd"))


class ElapsedTest(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual("45 s", console95.elapsed(45))

    def test_minutes(self):
        self.assertEqual("3 min 05 s", console95.elapsed(185))

    def test_hours(self):
        self.assertEqual("1 h 02 min", console95.elapsed(3720))


def _state(steps=12, at=3, fraction=0.4):
    s = console95.State(["Installing to C:\\Users\\Niccol\u00f2\\raccontami", "Languages: English, Italian"],
                        [f"Step number {i}" for i in range(steps)], "C:\\Users\\Niccol\u00f2\\raccontami\\setup-log.txt", started=0.0)
    for i in range(at):
        s.status[i] = "done"
    s.status[at] = "run"
    s.current, s.step_started, s.detail, s.fraction = at, 0.0, "Downloading torch 2.11.0+cu128 (2.9 GB)", fraction
    return s


class FrameTest(unittest.TestCase):
    def _widths(self, cols, rows, **kw):
        lines = console95.frame(_state(**kw), cols, rows, now=100.0)
        return {len(console95.visible(line)) for line in lines[:-1]}, len(lines)

    def test_every_line_is_as_wide_as_the_console(self):
        self.assertEqual({120}, self._widths(120, 30)[0])

    def test_as_many_lines_as_the_console_has(self):
        self.assertEqual(30, self._widths(120, 30)[1])

    def test_the_last_line_leaves_its_last_cell_free(self):  # writing it would scroll the screen
        self.assertEqual(119, len(console95.visible(console95.frame(_state(), 120, 30, now=100.0)[-1])))

    def test_a_small_console_still_gets_full_lines(self):
        self.assertEqual({50}, self._widths(50, 14, steps=20, at=15)[0])

    def test_a_small_console_gets_no_more_lines_than_it_has(self):
        self.assertEqual(14, self._widths(50, 14, steps=20, at=15)[1])

    def test_without_a_known_end_the_bar_still_fits(self):
        self.assertEqual({100}, self._widths(100, 40, fraction=None)[0])


class StepRowsTest(unittest.TestCase):
    def test_with_two_lines_the_running_step_stays_in_view(self):
        rows = console95._step_rows(_state(steps=12, at=6), 2, 60, now=100.0)
        self.assertTrue(any("Step number 6" in console95.visible(r.text()) for r in rows))


def _contrast(a, b):
    def lum(rgb):
        lin = [(v / 255) / 12.92 if v / 255 <= 0.03928 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class LegibleStepsTest(unittest.TestCase):
    def test_every_text_colour_of_the_step_list_reads_on_the_window(self):  # WCAG 4.5:1, also for steps not started
        s = _state(steps=6, at=3)
        s.status[1] = "skip"
        colours = {fg for row in console95._step_rows(s, 6, 70, now=100.0) for (fg, bg, _), text in row.parts if text.strip()}
        self.assertTrue(all(_contrast(fg, console95.FACE) >= 4.5 for fg in colours))


class StalledBarTest(unittest.TestCase):
    def _lit(self, now):
        s = _state(fraction=0.5)
        s.changed = 0.0
        return console95.visible(console95._bar(s, 40, now).text()).count("█")

    def test_a_bar_that_has_not_moved_for_a_while_blinks_its_next_block(self):  # the step is alive, not stuck
        self.assertNotEqual(self._lit(10.0), self._lit(10.5))

    def test_a_bar_that_just_moved_does_not_blink(self):
        self.assertEqual(self._lit(1.0), self._lit(1.5))


class ScreenTest(unittest.TestCase):
    def setUp(self):
        import io
        import tempfile
        self.folder = tempfile.mkdtemp()
        self.log = Path(self.folder) / "setup-log.txt"
        self.out = io.StringIO()
        self.screen = console95.Screen(["info"], ["A step"], self.log, fancy=False, out=self.out)

    def tearDown(self):
        import shutil
        self.screen.close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def _feed(self, *lines):
        with self.screen:
            self.screen.begin(0)
            for line in lines:
                self.screen.feed(line)
            self.screen.end(0, "fail")
        return self.log.read_text(encoding="utf-8")

    def test_progress_lines_stay_out_of_the_log(self):
        self.assertNotIn("Progress 1 of 2", self._feed("Collecting torch", "Progress 1 of 2"))

    def test_other_lines_go_to_the_log(self):
        self.assertIn("ERROR: no such version", self._feed("Progress 1 of 2", "ERROR: no such version"))

    def test_the_last_lines_are_kept_for_a_failure(self):
        self._feed("Collecting voxcpm", "Progress 5 of 9", "ERROR: no such version")
        self.assertEqual(["Collecting voxcpm", "ERROR: no such version"], self.screen.last_lines())


if __name__ == "__main__":
    unittest.main()
