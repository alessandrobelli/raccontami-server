"""Run from the repository root with:  python -m unittest discover tests"""

import tempfile
import unittest
from pathlib import Path

from raccontami_sync import background, single
from raccontami_sync import unfinished as u


class SingleTest(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())

    def test_the_first_server_gets_the_folder(self):
        lock = single.take(self.data)
        self.addCleanup(lock.close)
        self.assertIsNotNone(lock)

    def test_a_second_server_on_the_same_folder_is_refused(self):
        lock = single.take(self.data)
        self.addCleanup(lock.close)
        self.assertIsNone(single.take(self.data))

    def test_the_folder_is_free_again_when_the_first_has_ended(self):
        single.take(self.data).close()
        lock = single.take(self.data)
        self.addCleanup(lock.close)
        self.assertIsNotNone(lock)


class FailureTextTest(unittest.TestCase):
    def test_the_servers_own_explanation_is_what_is_shown(self):
        log = "18:00:01  NOT STARTED: a Raccontami server is already running on F:\\x. Use that one\nTraceback ..."
        self.assertEqual("a Raccontami server is already running on F:\\x. Use that one", background.failure_text(log))

    def test_a_taken_port_is_said_in_words(self):
        self.assertIn("already in use", background.failure_text("ERROR: [Errno 10048] error while attempting to bind"))

    def test_otherwise_the_last_lines_are_shown(self):
        self.assertIn("ModuleNotFoundError: No module named 'torch'",
                      background.failure_text("a\nb\nModuleNotFoundError: No module named 'torch'\n"))

    def test_an_empty_log_still_gives_a_message(self):
        self.assertIn("left no explanation", background.failure_text(""))

    def test_the_server_is_started_on_the_port_asked_for(self):
        self.assertEqual(["--port", "9000"], background.command(Path("python.exe"), "0.0.0.0", 9000)[6:8])


class PatientTest(unittest.TestCase):
    """The question at the start gives up when nobody answers."""

    def job(self, name, state):
        d = Path(tempfile.mkdtemp()) / name
        (d / "pieces").mkdir(parents=True)
        return d, {"state": state, "kind": "narrate"}

    @staticmethod
    def never(_question):
        import time
        time.sleep(30)
        return "y"

    def test_an_answer_in_time_is_taken(self):
        self.assertEqual("n", u.patient(lambda q: "n", 5)("?"))

    def test_without_an_answer_it_ends_as_if_there_were_nobody(self):
        with self.assertRaises(EOFError):
            u.patient(self.never, 0.2)("?")

    def test_after_giving_up_it_does_not_ask_again(self):
        asked = []

        def ask(question):
            asked.append(question)
            return self.never(question)

        patient = u.patient(ask, 0.2)
        for _ in range(2):
            with self.assertRaises(EOFError):
                patient("?")
        self.assertEqual(1, len(asked))

    def test_nobody_answering_continues_what_was_running_and_deletes_nothing(self):
        found = [self.job("n1", "running"), self.job("n2", u.HELD)]
        self.assertEqual({"n1": u.CONTINUE, "n2": u.LEAVE}, u.choose(found, ask=self.never, say=lambda s: None, seconds=0.2))

    def test_no_and_then_silence_keeps_the_work_on_hold(self):
        answers = iter(["n"])

        def ask(question):
            try:
                return next(answers)
            except StopIteration:
                return self.never(question)

        self.assertEqual({"n1": u.HOLD}, u.choose([self.job("n1", "running")], ask=ask, say=lambda s: None, seconds=0.2))

    def test_the_wait_is_a_setting(self):
        self.assertEqual(5.0, u.wait_seconds({"RACCONTAMI_ASK_SECONDS": "5"}))

    def test_zero_waits_for_ever(self):
        self.assertIs(input, u.patient(input, u.wait_seconds({"RACCONTAMI_ASK_SECONDS": "0"})))

    def test_a_wrong_setting_gives_the_usual_wait(self):
        self.assertEqual(60.0, u.wait_seconds({"RACCONTAMI_ASK_SECONDS": "soon"}))


if __name__ == "__main__":
    unittest.main()
