"""Run from the repository root with:  python -m unittest discover tests"""

import tempfile
import unittest
from pathlib import Path

from raccontami_sync import gpu_share


class Clock:
    """A clock that moves only when work is done or the pacer sleeps."""

    def __init__(self):
        self.now, self.slept = 0.0, []

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.slept.append(s)
        self.now += s


def paced(share, work_s):
    clock = Clock()
    pacer = gpu_share.Pacer(lambda: share, clock=clock, sleep=clock.sleep)
    clock.now += work_s
    pacer.step()
    return clock.slept


class PacerTest(unittest.TestCase):
    def test_at_full_share_it_never_waits(self):
        self.assertEqual([], paced(100, 2.0))

    def test_at_half_it_waits_as_long_as_it_worked(self):
        self.assertEqual([2.0], paced(50, 2.0))

    def test_at_a_quarter_it_waits_three_times_as_long(self):
        self.assertEqual([3.0], paced(25, 1.0))

    def test_a_pause_is_never_longer_than_the_limit(self):
        self.assertEqual([gpu_share.MAX_PAUSE_S], paced(10, 60.0))

    def test_the_pause_does_not_count_as_work_for_the_next_step(self):
        clock = Clock()
        pacer = gpu_share.Pacer(lambda: 50, clock=clock, sleep=clock.sleep)
        for _ in range(2):
            clock.now += 1.0
            pacer.step()
        self.assertEqual([1.0, 1.0], clock.slept)

    def test_a_change_of_share_applies_at_the_next_step(self):
        clock, share = Clock(), [100]
        pacer = gpu_share.Pacer(lambda: share[0], clock=clock, sleep=clock.sleep)
        clock.now += 1.0
        pacer.step()
        share[0] = 50
        clock.now += 1.0
        pacer.step()
        self.assertEqual([1.0], clock.slept)


class ParseTest(unittest.TestCase):
    def test_a_number_is_read(self):
        self.assertEqual(50, gpu_share.parse("50"))

    def test_a_percent_sign_and_spaces_are_allowed(self):
        self.assertEqual(25, gpu_share.parse(" 25 % "))

    def test_too_little_is_raised_to_the_lowest(self):
        self.assertEqual(gpu_share.LOWEST, gpu_share.parse("0"))

    def test_too_much_is_full(self):
        self.assertEqual(100, gpu_share.parse("250"))

    def test_words_are_not_a_share(self):
        self.assertIsNone(gpu_share.parse("half"))


class FileTest(unittest.TestCase):
    def test_what_is_written_is_read_back(self):
        f = Path(tempfile.mkdtemp()) / gpu_share.FILE
        gpu_share.write(f, 40)
        self.assertEqual(40, gpu_share.read(f))

    def test_without_the_file_it_is_full(self):
        self.assertEqual(100, gpu_share.read(Path(tempfile.mkdtemp()) / gpu_share.FILE))

    def test_a_file_that_makes_no_sense_is_full(self):
        f = Path(tempfile.mkdtemp()) / gpu_share.FILE
        f.write_text("plenty", encoding="utf-8")
        self.assertEqual(100, gpu_share.read(f))


if __name__ == "__main__":
    unittest.main()
