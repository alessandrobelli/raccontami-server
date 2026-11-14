"""Run from the repository root with:  python -m unittest discover tests"""

import unittest

from raccontami_sync import serve


class Loop:
    def __init__(self):
        self.shown = []

    def default_exception_handler(self, context):
        self.shown.append(context)


LOST = "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)"


class QuietDropsTest(unittest.TestCase):
    def test_a_phone_that_hung_up_is_not_shown(self):
        loop = Loop()
        serve.quiet_drops(loop, {"message": LOST, "exception": ConnectionResetError(10054, "forcibly closed")})
        self.assertEqual([], loop.shown)

    def test_another_error_while_a_connection_ends_is_shown(self):
        loop = Loop()
        serve.quiet_drops(loop, {"message": LOST, "exception": ValueError("something else")})
        self.assertEqual(1, len(loop.shown))

    def test_a_reset_anywhere_else_is_shown(self):
        loop = Loop()
        serve.quiet_drops(loop, {"message": "Task exception was never retrieved", "exception": ConnectionResetError()})
        self.assertEqual(1, len(loop.shown))

    def test_an_error_without_an_exception_is_shown(self):
        loop = Loop()
        serve.quiet_drops(loop, {"message": "something went wrong"})
        self.assertEqual(1, len(loop.shown))


if __name__ == "__main__":
    unittest.main()
