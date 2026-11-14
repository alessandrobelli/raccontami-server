"""Run from the repository root with:  python -m unittest discover tests"""

import unittest

from raccontami_sync import connect_window, tray


class TrayTest(unittest.TestCase):
    def test_the_port_is_read_from_how_the_server_was_started(self):
        self.assertEqual(9000, tray.own_port(["uvicorn", "app:app", "--port", "9000"], {}))

    def test_the_port_written_with_an_equals_sign_is_read_too(self):
        self.assertEqual(9001, tray.own_port(["uvicorn", "--port=9001"], {}))

    def test_without_one_the_setting_is_used(self):
        self.assertEqual(9002, tray.own_port(["python"], {"RACCONTAMI_PORT": "9002"}))

    def test_without_either_it_is_the_usual_port(self):
        self.assertEqual(8765, tray.own_port(["python"], {}))

    def test_the_page_is_https_when_the_link_is_encrypted(self):
        self.assertEqual("https://localhost:8765/", tray.own_url(["python"], {"RACCONTAMI_TLS_CODE": "AB12"}))

    def test_the_page_is_http_without_the_encrypted_link(self):
        self.assertEqual("http://localhost:9000/", tray.own_url(["python"], {"RACCONTAMI_PORT": "9000"}))

    def test_no_icon_outside_windows(self):
        self.assertIsNotNone(tray.why_not("linux", {}))

    def test_no_icon_when_switched_off(self):
        self.assertIsNotNone(tray.why_not("win32", {"RACCONTAMI_TRAY": "0"}))

    def test_an_icon_on_windows(self):
        self.assertIsNone(tray.why_not("win32", {}))

    def test_what_the_app_asks_for_is_said_with_the_code_to_compare(self):
        rows = connect_window.facts("https://192.168.1.4:8765", "abc", "token.txt", "3fa9-07c2-b1d4-88e0")
        self.assertEqual(["https://192.168.1.4:8765", "abc", "3fa9-07c2-b1d4-88e0"], [value for _, value, _ in rows])

    def test_without_the_encrypted_link_there_is_no_code_to_compare(self):
        rows = connect_window.facts("http://192.168.1.4:8765", "abc", "token.txt", None)
        self.assertIn("no code to compare", connect_window.as_text(rows))

    def test_being_switched_off_never_raises_and_gives_no_icon(self):
        said = []
        import os
        before = os.environ.get("RACCONTAMI_TRAY")
        os.environ["RACCONTAMI_TRAY"] = "0"
        try:
            self.assertIsNone(tray.start("x", None, None, None, None, None, said.append))
        finally:
            if before is None:
                del os.environ["RACCONTAMI_TRAY"]
            else:
                os.environ["RACCONTAMI_TRAY"] = before
        self.assertIn("none", said[0])


if __name__ == "__main__":
    unittest.main()
