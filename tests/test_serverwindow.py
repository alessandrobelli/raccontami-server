"""Run from the repository root with:  python -m unittest discover tests

The server's window drawn like Windows 95 (raccontami_sync/serverwindow.py)."""

import io
import unittest

from raccontami_sync import console95, serverwindow

SECTIONS = [("CONNECT THE PHONE   in the app: Settings → Server",
             [("Address", "https://192.168.1.4:8765", "Or tap Search local network in the app.")]),
            ("THIS SERVER", [("GPU", "RTX 5080", ""), ("Voices", "Italian: VoxCPM2\nEnglish: Qwen3-TTS", "")])]


class Console(io.StringIO):
    def isatty(self):
        return True


def window(cols=100):
    out = Console()
    w = serverwindow.ServerWindow(out, size=lambda: (cols, 30), status=lambda: (("working", "syncing, 40 %"), "https://localhost:8765/"))
    return w, out


def lines(text):
    """The drawn lines, without colours and cursor moves."""
    return [console95.visible(line) for line in text.replace("\r", "").split("\n") if console95.visible(line).strip()]


class MarkTest(unittest.TestCase):
    def test_a_finished_job_gets_a_tick(self):
        self.assertEqual("√", serverwindow.mark("sync 1a2b3c4d: done in 16 min")[0])

    def test_a_failed_job_gets_a_cross(self):
        self.assertEqual("×", serverwindow.mark("sync 1a2b3c4d: FAILED: out of memory")[0])

    def test_a_failure_is_drawn_in_the_danger_colour(self):
        self.assertEqual(console95.RED, serverwindow.mark("adding Turkish failed: no network")[1])

    def test_a_started_job_gets_an_arrow(self):
        self.assertEqual("►", serverwindow.mark("narration 1a2b3c4d: started")[0])

    def test_progress_gets_no_mark(self):
        self.assertEqual(" ", serverwindow.mark("sync 1a2b3c4d: 40 %, about 9 min left")[0])


class BlockTest(unittest.TestCase):
    def test_every_line_of_the_block_is_as_wide_as_the_console(self):
        w, out = window(100)
        w.block("Raccontami Server 0.4.0", SECTIONS)
        self.assertEqual({99}, {len(line) for line in lines(out.getvalue())})  # the last cell is erased, not written

    def test_a_section_title_reads_as_a_sentence(self):
        w, out = window()
        w.block("Raccontami Server 0.4.0", SECTIONS)
        self.assertIn("─ Connect the phone ", console95.visible(out.getvalue()))

    def test_a_long_note_loses_no_letter_when_wrapped(self):
        words = [f"word{i}" for i in range(60)]
        w, out = window(100)
        w.block("Raccontami Server 0.4.0", [("THIS SERVER", [("Icon", "next to the clock", " ".join(words))])])
        shown = " ".join(console95.visible(out.getvalue()).split())
        self.assertTrue(all(f" {word} " in shown for word in words))

    def test_a_long_value_loses_no_letter_when_wrapped(self):
        path = "C:\\" + "\\".join(f"folder{i}" for i in range(30))
        w, out = window(100)
        w.block("Raccontami Server 0.4.0", [("THIS SERVER", [("Data", path, "")])])
        text = console95.visible(out.getvalue())
        self.assertIn(path, "".join(line.split("│")[2].strip() if line.count("│") >= 3 else "" for line in text.split("\n") if "folder" in line))

    def test_every_line_of_a_value_is_shown(self):
        w, out = window()
        w.block("Raccontami Server 0.4.0", SECTIONS)
        self.assertIn("English: Qwen3-TTS", out.getvalue())


class ActivityTest(unittest.TestCase):
    def test_every_activity_line_is_as_wide_as_the_console(self):
        w, out = window(90)
        w.line("13:02:11", "sync 1a2b3c4d: received from the phone, Italian, 41,203 words, " + "very long " * 20)
        self.assertEqual({89}, {len(line) for line in lines(out.getvalue())})

    def test_the_status_bar_says_what_the_server_does(self):
        w, out = window()
        w.line("13:02:11", "sync 1a2b3c4d: started")
        self.assertIn("syncing, 40 %", out.getvalue())

    def test_the_next_line_takes_the_place_of_the_status_bar(self):  # the window grows, its foot stays at the bottom
        w, out = window()
        w.line("13:02:11", "sync 1a2b3c4d: started")
        w.line("13:09:40", "sync 1a2b3c4d: 40 %")
        self.assertIn(f"\x1b[{serverwindow.FOOT}F", out.getvalue())

    def test_one_window_holds_lines_in_a_row(self):
        w, out = window()
        w.line("13:02:11", "sync 1a2b3c4d: started")
        w.line("13:09:40", "sync 1a2b3c4d: 40 %")
        self.assertEqual(1, out.getvalue().count("Activity"))

    def test_after_other_output_a_new_window_opens(self):  # nothing printed by others is drawn over
        w, out = window()
        w.line("13:02:11", "sync 1a2b3c4d: started")
        w.tap(out).write("a warning from a library\n")
        w.line("13:09:40", "sync 1a2b3c4d: 40 %")
        self.assertEqual(2, out.getvalue().count("Activity"))

    def test_after_other_output_the_foot_is_not_drawn_over(self):
        w, out = window()
        w.line("13:02:11", "sync 1a2b3c4d: started")
        w.tap(out).write("a warning from a library\n")
        before = out.getvalue()
        w.line("13:09:40", "sync 1a2b3c4d: 40 %")
        self.assertNotIn(f"\x1b[{serverwindow.FOOT}F", out.getvalue()[len(before):])


if __name__ == "__main__":
    unittest.main()
