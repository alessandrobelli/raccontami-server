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

    # the story's name and who tells it

    def test_a_job_with_a_name_is_told_by_it(self):
        d, _ = self.job("n1", state="running", kind="narrate")
        u.write_label(d, "La Divina Commedia", "SM-S931B")
        self.assertTrue(u.about(d, "narrate").startswith('"La Divina Commedia": a narration, Italian'))

    def test_the_device_that_sent_it_is_kept(self):
        d, _ = self.job("n1", state="running", kind="narrate")
        u.write_label(d, "x", "SM-S931B")
        self.assertEqual("SM-S931B", u.facts(d, "narrate")["device"])

    def test_a_name_that_is_not_text_is_not_kept(self):
        d, _ = self.job("n1", state="running", kind="narrate")
        u.write_label(d, {"a": 1}, None)
        self.assertIsNone(u.facts(d, "narrate")["title"])

    def test_a_very_long_name_is_cut(self):
        d, _ = self.job("n1", state="running", kind="narrate")
        u.write_label(d, "x" * 5000, None)
        self.assertEqual(200, len(u.facts(d, "narrate")["title"]))

    def test_without_narrators_there_is_one_voice(self):
        d, _ = self.job("n1", state="running", kind="narrate")
        self.assertEqual((0, 1), (u.facts(d, "narrate")["narrators"], u.facts(d, "narrate")["voices"]))

    def test_narrators_without_a_voice_of_their_own_share_one(self):
        d, _ = self.job("n1", state="running", kind="narrate")
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        meta.update(narrators=[[0, "Anna"], [1, "Marco"], [2, "Nilo"]], cast={"Anna": "seta"})
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual((3, 2), (u.facts(d, "narrate")["narrators"], u.facts(d, "narrate")["voices"]))

    def test_the_pieces_planned_are_the_ones_that_are_spoken(self):
        d, _ = self.job("n1", state="running", kind="narrate")
        (d / "plan.json").write_text(json.dumps({"pieces": [{"i": 0, "say": "a"}, {"i": 1, "say": ""}, {"i": 2, "say": "b"}]}),
                                     encoding="utf-8")
        self.assertEqual(2, u.pieces_total(d))

    def test_before_it_is_planned_the_number_of_pieces_is_not_known(self):
        d, _ = self.job("n1", state="queued", kind="narrate")
        self.assertIsNone(u.pieces_total(d))

    # what the server's page may continue

    def test_a_job_on_hold_can_be_continued(self):
        self.assertTrue(u.can_continue(*self.job("n1", state=u.HELD, kind="narrate")))

    def test_a_failed_narration_with_pieces_can_be_continued(self):
        self.assertTrue(u.can_continue(*self.job("n1", pieces=3, state="failed", kind="narrate")))

    def test_a_running_job_has_nothing_to_continue(self):
        self.assertFalse(u.can_continue(*self.job("n1", state="running", kind="narrate")))

    def test_a_waiting_job_has_nothing_to_continue(self):
        self.assertFalse(u.can_continue(*self.job("n1", state="queued", kind="narrate")))

    def test_a_finished_job_has_nothing_to_continue(self):
        self.assertFalse(u.can_continue(*self.job("n1", pieces=3, state="done", kind="narrate")))

    # what may be deleted, from the page or by the phone

    def test_a_narration_can_be_deleted_while_it_runs(self):
        self.assertTrue(u.can_delete({"state": "running", "kind": "narrate"}))

    def test_a_waiting_sync_can_be_deleted(self):
        self.assertTrue(u.can_delete({"state": "queued", "kind": "sync"}))

    def test_a_sync_on_hold_can_be_deleted(self):
        self.assertTrue(u.can_delete({"state": u.HELD, "kind": "sync"}))

    def test_a_failed_sync_can_be_deleted(self):
        self.assertTrue(u.can_delete({"state": "failed", "kind": "sync"}))

    def test_a_running_sync_cannot_be_deleted(self):
        self.assertFalse(u.can_delete({"state": "running", "kind": "sync"}))

    def test_a_sync_is_told_as_a_sync(self):
        d, _ = self.job("a1", state="running", kind="sync")
        self.assertIn("A sync of an audiobook", u.about(d, "sync"))

    def test_a_window_without_a_keyboard_is_not_asked(self):
        class Piped:
            def isatty(self):
                return False
        self.assertFalse(u.interactive(Piped(), Piped()))


class PageFactsTest(unittest.TestCase):
    """What the server's page says about a job besides its progress."""

    def test_a_jobs_size_is_the_sum_of_its_files_in_every_folder(self):
        d = Path(tempfile.mkdtemp())
        (d / "pieces").mkdir()
        (d / "audio.m4a").write_bytes(b"x" * 10)
        (d / "pieces" / "1.wav").write_bytes(b"x" * 5)
        self.assertEqual(15, u.folder_bytes(d))

    def test_a_folder_that_is_gone_takes_no_room(self):
        self.assertEqual(0, u.folder_bytes(Path(tempfile.mkdtemp()) / "deleted"))

    def test_running_out_of_graphics_memory_is_said_in_words(self):
        self.assertIn("graphics card ran out of memory",
                      u.explain("RuntimeError: CUDA out of memory. Tried to allocate 2.50 GiB"))

    def test_a_full_disk_is_said_in_words(self):
        self.assertIn("disk is full", u.explain("OSError: [Errno 28] No space left on device"))

    def test_an_unknown_failure_has_no_explanation(self):
        self.assertIsNone(u.explain("ValueError: something nobody has seen"))

    def test_no_error_has_no_explanation(self):
        self.assertIsNone(u.explain(None))

if __name__ == "__main__":
    unittest.main()
