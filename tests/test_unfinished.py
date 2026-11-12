"""Run from the repository root with:  python -m unittest discover tests"""

import json
import tempfile
import unittest
from pathlib import Path

from raccontami_sync import unfinished as u


def answers(*given):
    """An ask() that gives these answers in turn, then ends like a window without a keyboard."""
    left = list(given)

    def ask(_question):
        if not left:
            raise EOFError
        return left.pop(0)
    return ask


class UnfinishedTest(unittest.TestCase):
    def setUp(self):
        self.jobs = Path(tempfile.mkdtemp())
        self.said = []

    def job(self, name, pieces=0, **status):
        d = self.jobs / name
        (d / "pieces").mkdir(parents=True)
        for i in range(pieces):
            (d / "pieces" / f"{i:05d}.wav").write_bytes(b"")
        (d / "status.json").write_text(json.dumps(status), encoding="utf-8")
        (d / "meta.json").write_text(json.dumps({"lang": "it", "tokens": ["Nel", "mezzo", "del", "cammin"], "start": 1}),
                                     encoding="utf-8")
        return d, status

    def choose(self, found, *given):
        return u.choose(found, ask=answers(*given), say=self.said.append)

    # what counts as unfinished

    def test_a_job_that_was_running_is_unfinished(self):
        self.assertTrue(u.is_unfinished(*self.job("n1", state="running", kind="narrate")))

    def test_a_job_on_hold_is_unfinished(self):
        self.assertTrue(u.is_unfinished(*self.job("n1", state=u.HELD, kind="narrate")))

    def test_a_failed_narration_with_pieces_is_unfinished(self):
        self.assertTrue(u.is_unfinished(*self.job("n1", pieces=3, state="failed", kind="narrate")))

    def test_a_failed_narration_without_pieces_is_not(self):
        self.assertFalse(u.is_unfinished(*self.job("n1", state="failed", kind="narrate")))

    def test_a_failed_sync_is_not(self):
        self.assertFalse(u.is_unfinished(*self.job("a1", pieces=3, state="failed", kind="sync")))

    def test_a_finished_job_is_not(self):
        self.assertFalse(u.is_unfinished(*self.job("n1", pieces=3, state="done", kind="narrate")))

    # with nobody to ask

    def test_with_nobody_to_ask_a_running_job_continues(self):
        self.assertEqual(u.CONTINUE, u.default_choice({"state": "running"}))

    def test_with_nobody_to_ask_a_failed_narration_is_left_alone(self):
        self.assertEqual(u.LEAVE, u.default_choice({"state": "failed"}))

    def test_with_nobody_to_ask_a_job_on_hold_stays_on_hold(self):
        self.assertEqual(u.LEAVE, u.default_choice({"state": u.HELD}))

    # the answers

    def test_enter_alone_continues(self):
        self.assertEqual({"n1": u.CONTINUE}, self.choose([self.job("n1", state="running", kind="narrate")], ""))

    def test_no_then_enter_keeps_the_work_on_hold(self):
        self.assertEqual({"n1": u.HOLD}, self.choose([self.job("n1", state="running", kind="narrate")], "n", ""))

    def test_no_then_yes_deletes(self):
        self.assertEqual({"n1": u.DELETE}, self.choose([self.job("n1", state="running", kind="narrate")], "n", "y"))

    def test_an_unclear_answer_is_asked_again(self):
        self.assertEqual({"n1": u.HOLD}, self.choose([self.job("n1", state="running", kind="narrate")], "maybe", "no", "n"))

    def test_each_job_gets_its_own_answer(self):
        found = [self.job("n1", state="running", kind="narrate"), self.job("n2", pieces=2, state="failed", kind="narrate")]
        self.assertEqual({"n1": u.CONTINUE, "n2": u.HOLD}, self.choose(found, "y", "n", "n"))

    def test_when_the_answers_end_nothing_is_deleted(self):
        found = [self.job("n1", state="running", kind="narrate"), self.job("n2", pieces=2, state="failed", kind="narrate")]
        self.assertEqual({"n1": u.CONTINUE, "n2": u.LEAVE}, self.choose(found))

    def test_when_the_answers_end_after_a_no_the_work_is_kept_and_not_started(self):
        self.assertEqual({"n1": u.HOLD}, self.choose([self.job("n1", state="running", kind="narrate")], "n"))

    # what the reader is told

    def test_a_narration_is_told_by_its_first_narrated_words_and_its_pieces(self):
        d, s = self.job("n1", pieces=2, state="failed", kind="narrate", progress=0.3)
        text = " ".join(u.describe(d, s))
        self.assertIn('beginning "mezzo del cammin ..."', text)
        self.assertIn("30 % done, 2 pieces of audio already made", text)

    def test_a_job_without_readable_details_is_still_described(self):
        d, s = self.job("n1", state="running", kind="narrate")
        (d / "meta.json").write_text("{broken", encoding="utf-8")
        self.assertIn("A narration", u.describe(d, s)[0])

    def test_a_window_without_a_keyboard_is_not_asked(self):
        class Piped:
            def isatty(self):
                return False
        self.assertFalse(u.interactive(Piped(), Piped()))


if __name__ == "__main__":
    unittest.main()
