"""The server's window drawn like Windows 95, as the installer's setup window is (console95.py): a teal
desktop, the start-up block as a gray window with a navy title bar, and the log in an "Activity" window
that grows downward, its status bar (what the server is doing, the page, the clock) always at its foot.

It stays a scrolling log on purpose: scrolling back and copying text still work, and server.log is
written as before, in plain text (app.py). Each new log line takes the place of the status bar and draws
it again under itself. Anything else that writes to the window (a library's warning, the question about
unfinished work) is noticed on its way through sys.stdout and sys.stderr: nothing is drawn over it, and
the next log line opens a new Activity window below it.

Only in a real console (console95.console_ready); started without a window, or with the output going to
a file, the server prints its plain lines as before.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import textwrap
import threading
import time

from .console95 import BLACK, DARK, FACE, LIGHT, NAVY, PRESSED, RED, TEAL, Row, console_ready

FOOT = 4            # the lines under the last log line: separator, status bar, bottom edge, shadow
WIDE = 112          # the widest a window gets
NAME = 12           # the name column of the start-up block
TIME = 8            # "13:02:11"
FOREIGN = "\x1b[0;38;2;255;255;255;48;2;0;128;128m"  # what others print: white on the desktop, never drawn over
REFRESH = 20        # seconds between redraws of the status bar (its clock), while nothing else was printed
WORDS = {"working": "Working", "hold": "On hold", "idle": "Idle"}

current: ServerWindow | None = None  # set by install(): app.log() draws through it


def mark(msg: str) -> tuple[str, tuple]:
    """The glyph in front of a log line, and its colour: × a failure, √ something finished, ► a start."""
    low = msg.lower()
    if "failed" in low:
        return "×", RED
    if ": done" in low or "ready for the phone" in low or low.startswith("language added") or low.endswith("is running"):
        return "√", BLACK
    if low.endswith(": started") or ": started (" in low or "received from the phone" in low or "sent again from the phone" in low:
        return "►", BLACK
    return " ", BLACK


class Tap:
    """sys.stdout or sys.stderr, passed through: a write that is not the window's own is noticed."""

    def __init__(self, raw, window: ServerWindow):
        self._raw, self._window = raw, window

    def write(self, text):
        if text:
            self._window.foreign()
        return self._raw.write(text)

    def __getattr__(self, name):
        return getattr(self._raw, name)


class ServerWindow:
    def __init__(self, out, size=None, status=None):
        self.out = out
        self.size = size or (lambda: shutil.get_terminal_size((100, 30)))
        self.status = status          # () -> ((word, text), page url); set by app.py once it knows
        self.lock = threading.RLock()
        self.open = False             # an Activity window is open (its foot is the last thing drawn)
        self.foot_last = False        # nothing was printed under that foot since
        self.stopping = threading.Event()

    def tap(self, raw) -> Tap:
        return Tap(raw, self)

    def foreign(self) -> None:
        self.foot_last = False
        self.open = False

    # ---- geometry
    def _geometry(self):
        cols = max(20, self.size()[0])
        margin = cols >= 44
        width = min(cols - 4, WIDE) if margin else cols - 1
        return cols, margin, width

    def _screen_line(self, window_row: Row | None, cols: int, margin: bool, shadow: bool = True) -> str:
        """One console line: desktop, the window's row, its shadow, desktop to the end. The last cell is
        filled by erasing, never written, so a full line does not wrap."""
        row = Row()
        if margin:
            row.add("  ", TEAL, TEAL)
        if window_row is not None:
            row.join(window_row)
            if margin:
                row.add(" ", BLACK, BLACK if shadow else TEAL)
        return row.fill(cols - 1, TEAL).cut(cols - 1).text() + FOREIGN + "\x1b[K\n"

    def _shadow_line(self, cols: int, margin: bool, width: int) -> str:
        if not margin:
            return self._screen_line(None, cols, margin)
        return Row().add("   ", TEAL, TEAL).add(" " * width, BLACK, BLACK).fill(cols - 1, TEAL).cut(cols - 1).text() + FOREIGN + "\x1b[K\n"

    @staticmethod
    def _framed(content: Row, width: int) -> Row:
        return Row().add("│", LIGHT).join(content.cut(width - 2)).add("│", DARK)

    def _top(self, width: int, title: str) -> list[Row]:
        inner = width - 2
        bar = Row().add("│", LIGHT)
        buttons = inner >= 34
        text = " ■ " + title
        bar.add(text[:inner - (11 if buttons else 0)].ljust(inner - (11 if buttons else 0)), LIGHT, NAVY, bold=True)
        if buttons:
            bar.add(" _ ", BLACK, FACE).add(" □ ", BLACK, FACE).add(" ", NAVY, NAVY).add(" × ", BLACK, FACE, bold=True).add(" ", NAVY, NAVY)
        return [Row().add("┌" + "─" * inner, LIGHT).add("┐", DARK), bar.add("│", DARK)]

    # ---- the start-up block
    def block(self, title: str, sections) -> None:
        """The start-up block (the same sections banner.py prints) as a window with a group box each."""
        with self.lock:
            cols, margin, width = self._geometry()
            inner, group = width - 2, width - 6
            text = group - 2
            rows = self._top(width, title) + [self._framed(Row(), width)]
            for heading, items in sections:
                if not items:
                    continue
                name, _, sub = heading.partition("   ")
                label = " " + name.strip().capitalize() + " "
                rows.append(self._framed(Row().add("  ").add("┌─", DARK).add(label).add("─" * max(0, group - 3 - len(label)) + "┐", DARK), width))
                body = [Row().add(sub.strip())] if sub.strip() else []
                for key, value, note in items:
                    first = True
                    for part in value.split("\n"):
                        for piece in textwrap.wrap(part, text - NAME - 2, break_long_words=True) or [""]:
                            body.append(Row().add((key if first else "").ljust(NAME)).add(" ").add(piece, bold=True))
                            first = False
                    for piece in textwrap.wrap(note, text - NAME - 2):
                        body.append(Row().add(" " * (NAME + 1)).add(piece))
                for line in body:
                    rows.append(self._framed(Row().add("  ").add("│", DARK).add(" ").join(line.cut(text - 1)).add("│", LIGHT), width))
                rows.append(self._framed(Row().add("  ").add("└" + "─" * (group - 2) + "┘", LIGHT), width))
                rows.append(self._framed(Row(), width))
            rows.append(Row().add("└" + "─" * inner + "┘", DARK))
            out = [self._screen_line(r, cols, margin, shadow=i > 0) for i, r in enumerate(rows)]
            out.append(self._shadow_line(cols, margin, width))
            out.append(self._screen_line(None, cols, margin))
            self._write("".join(out))
            self.open = self.foot_last = False

    # ---- the log
    def _foot(self, cols: int, margin: bool, width: int) -> list[str]:
        inner = width - 2
        word, text, page = "Starting", "", ""
        if self.status:
            try:
                (state, text), page = self.status()
                word = WORDS.get(state, state)
            except Exception:  # noqa: BLE001  the status bar never stops the log
                pass
        clock = " " + time.strftime("%H:%M") + " "
        bar = Row().add(" ").add(word, bold=True)
        for piece in (text, f"Page {page}" if page else ""):
            if piece:
                bar.add(" │ ", DARK).add(piece)
        bar = bar.cut(inner - len(clock) - 1).add(" ").add(clock, BLACK, PRESSED)
        rows = [Row().add("├" + "─" * inner, DARK).add("┤", DARK), self._framed(bar, width), Row().add("└" + "─" * inner + "┘", DARK)]
        return [self._screen_line(r, cols, margin) for r in rows] + [self._shadow_line(cols, margin, width)]

    def line(self, stamp: str, msg: str) -> None:
        """One log line in the Activity window, under the last one; the status bar moves under it."""
        with self.lock:
            cols, margin, width = self._geometry()
            out = []
            if self.open and self.foot_last:
                out.append(f"\x1b[{FOOT}F")  # back to where the status bar starts: this line takes its place
            else:
                out += [self._screen_line(r, cols, margin, shadow=i > 0) for i, r in enumerate(self._top(width, "Activity"))]
            glyph, colour = mark(msg)
            room = width - 2 - (1 + TIME + 2 + 2)
            for i, piece in enumerate(textwrap.wrap(msg, room, break_long_words=True) or [""]):
                row = Row().add(" ").add(stamp if i == 0 else " " * TIME).add("  ")
                row.add((glyph if i == 0 else " ") + " ", colour, bold=glyph != " ").add(piece, RED if colour == RED else BLACK)
                out.append(self._screen_line(self._framed(row, width), cols, margin))
            out += self._foot(cols, margin, width)
            self._write("".join(out))
            self.open = self.foot_last = True

    def refresh(self) -> None:
        """The status bar again (its clock, what the server does), when nothing was printed under it."""
        with self.lock:
            if self.open and self.foot_last:
                cols, margin, width = self._geometry()
                self._write(f"\x1b[{FOOT}F" + "".join(self._foot(cols, margin, width)))

    def _tick(self) -> None:
        while not self.stopping.wait(REFRESH):
            self.refresh()

    def start(self) -> None:
        self._write(FOREIGN + "\x1b[2J\x1b[H")  # the desktop
        threading.Thread(target=self._tick, daemon=True).start()

    def close(self) -> None:
        self.stopping.set()
        self._write("\x1b[0m")

    def _write(self, text: str) -> None:
        try:
            self.out.write(text)
            self.out.flush()
        except (OSError, ValueError):  # the window was closed
            pass


def install() -> ServerWindow | None:
    """Turns the server's window into the Windows 95 one, when it is a real console. Before uvicorn starts,
    so that its own messages pass through too."""
    global current
    if os.environ.get("RACCONTAMI_WINDOWLESS") == "1" or os.environ.get("RACCONTAMI_PLAIN") or not console_ready(sys.stdout):
        return None
    window = ServerWindow(sys.stdout)
    sys.stdout, sys.stderr = window.tap(sys.stdout), window.tap(sys.stderr)
    window.start()
    atexit.register(window.close)
    current = window
    return window
