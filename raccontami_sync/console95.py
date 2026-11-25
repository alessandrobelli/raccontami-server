"""The installer's setup window, drawn like Windows 95: a teal desktop, a gray window with a navy title bar,
the steps with a tick when done, a block progress bar, a status bar and a taskbar with a clock.

The steps' output (pip, the model download) is read here instead of being written to the window: the
parts that say what is happening and how far it is become the window's text and bar, and everything else
goes to a log file. Where a step says nothing for minutes (unpacking, the graphics card at work) the bar
moves on its own and the clock keeps counting, so the window never looks stuck. A bar only fills when a
real total is known (bytes of a download, files of a model); otherwise it slides.

Standard library only: it runs on the installer's own Python before any environment exists. When the
output is not a console (redirected), the same steps print plain lines instead.

  python raccontami_sync/console95.py --demo [--fail]   (fake steps, nothing is installed)

The server's own window (serverwindow.py) is drawn with the same pieces.
"""

from __future__ import annotations

import collections
import datetime
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field

TITLE = "Raccontami Server Setup"
TEAL, FACE, LIGHT, DARK = (0, 128, 128), (192, 192, 192), (255, 255, 255), (128, 128, 128)
MUTED = (72, 72, 72)  # quieter text (steps not started, times): 5:1 on FACE; DARK is for bevel lines only
BLACK, NAVY, RED, PRESSED = (0, 0, 0), (0, 0, 128), (128, 0, 0), (212, 212, 212)
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def visible(text: str) -> str:
    return ANSI.sub("", text)


# ---- reading a step's output -------------------------------------------------------------------------

@dataclass
class Update:
    detail: str | None = None      # what the step is doing now, in words; None keeps the last one
    fraction: float | None = None  # how far, when a real total is known; with a detail, None means unknown
    log: bool = True               # worth keeping in the log (progress lines are not: thousands of them)
    extra: str | None = None       # text printed on the same line after a progress bar (a warning): for the log


def _package(name: str) -> str:
    """torch-2.11.0%2Bcu128-cp312-cp312-win_amd64.whl (or its address) -> torch 2.11.0+cu128"""
    base = urllib.parse.unquote(name.rsplit("/", 1)[-1])
    for ext in (".whl", ".tar.gz", ".zip"):
        base = base[:-len(ext)] if base.endswith(ext) else base
    parts = base.split("-")
    return f"{parts[0]} {parts[1]}" if len(parts) > 1 else parts[0]


def _requirement(spec: str) -> str:
    """sympy>=1.13.3 -> sympy"""
    return re.split(r"[<>=!~\[;(@ ]", spec.strip(), maxsplit=1)[0]


def _tqdm(m) -> Update:
    percent = min(100, int(m[2]))
    return Update(m[1].strip().rstrip(":").strip() or None, percent / 100, log=percent >= 100, extra=m[3].strip() or None)


RULES = [
    (r"Progress (\d+) of (\d+)$",  # pip --progress-bar raw
     lambda m: Update(fraction=min(1.0, int(m[1]) / int(m[2])) if int(m[2]) else 0.0, log=False)),
    (r"Downloading (\S+) \(([^)]+)\)$",
     lambda m: None if m[1].endswith(".metadata") else Update(f"Downloading {_package(m[1])} ({m[2]})", 0.0)),
    (r"Collecting (\S+)", lambda m: Update(f"Looking up {_requirement(m[1])}")),
    (r"Using cached (\S+) \(", lambda m: Update(f"Using a saved copy of {_package(m[1])}")),
    (r"Requirement already satisfied", lambda m: Update("Checking what is already installed")),
    (r"\s*Building wheels? for (\S+)", lambda m: Update(f"Building {m[1]}")),
    (r"Installing collected packages: (.+)",
     lambda m: Update(f"Installing {len(m[1].split(','))} packages (this takes a while)")),
    (r"Successfully installed", lambda m: Update("Installed")),
    (r"model (\d+) of (\d+): (.+)", lambda m: Update(f"Model {m[1]} of {m[2]}: {m[3]}")),  # tools/prefetch.py
    (r"all models ready", lambda m: Update("All the models are ready", 1.0)),
    (r"Making a narrator", lambda m: Update("Designing the voice on the graphics card (a few minutes)")),
    (r"Narrator saved", lambda m: Update("Narrator saved", 1.0)),
    (r"(.*?):?\s*(\d{1,3})%\|[^|]*\|[^\[]*(?:\[[^\]]*\])?(.*)$", _tqdm),  # Hugging Face and Whisper downloads
]
_RULES = [(re.compile(p), f) for p, f in RULES]


def read(line: str) -> Update | None:
    """What one line of a step's output says, or None when it is only for the log."""
    line = visible(line).rstrip()
    for pattern, make in _RULES:
        m = pattern.match(line)
        if m:
            return make(m)
    return None


def split_lines(buffer: bytes) -> tuple[list[str], bytes]:
    """Whole lines and the unfinished rest. A carriage return ends a line too: progress bars redraw with it."""
    parts = re.split(rb"\r\n|\r|\n", buffer)
    rest = parts.pop()
    return [p.decode("utf-8", "replace") for p in parts if p], rest


def elapsed(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60:02d} s"
    return f"{s // 3600} h {s % 3600 // 60:02d} min"


# ---- drawing ------------------------------------------------------------------------------------------

@dataclass
class State:
    info: list
    steps: list
    log_path: str
    started: float
    status: list = field(default_factory=list)   # todo, run, done, skip (already there), fail
    seconds: list = field(default_factory=list)
    current: int = -1
    step_started: float = 0.0
    detail: str = ""
    fraction: float | None = None
    changed: float = 0.0  # when the fraction last moved
    finished: bool = False

    def __post_init__(self):
        self.status = self.status or ["todo"] * len(self.steps)
        self.seconds = self.seconds or [None] * len(self.steps)


def _sgr(fg, bg, bold=False) -> str:
    return f"\x1b[{1 if bold else 22};38;2;{fg[0]};{fg[1]};{fg[2]};48;2;{bg[0]};{bg[1]};{bg[2]}m"


def _fit(text: str, width: int) -> str:
    if width <= 0:
        return ""
    return text.ljust(width) if len(text) <= width else text[:max(0, width - 1)] + "…"


class Row:
    """One line of the screen, built from coloured pieces; its width is counted as it grows. Pieces of
    the same colour are kept together, so a frame stays small to write."""

    def __init__(self):
        self.parts: list[list] = []  # [(fg, bg, bold), text]
        self.width = 0

    def add(self, text: str, fg=BLACK, bg=FACE, bold=False) -> Row:
        if text:
            style = (fg, bg, bold)
            if self.parts and self.parts[-1][0] == style:
                self.parts[-1][1] += text
            else:
                self.parts.append([style, text])
            self.width += len(text)
        return self

    def join(self, other: Row) -> Row:
        for style, text in other.parts:
            self.add(text, *style)
        return self

    def fill(self, width: int, bg=FACE) -> Row:
        return self.add(" " * max(0, width - self.width), bg=bg, fg=bg)

    def cut(self, width: int) -> Row:
        """This row cut, or filled, to exactly `width` cells."""
        out = Row()
        for style, text in self.parts:
            if out.width >= width:
                break
            out.add(text[:width - out.width], *style)
        return out.fill(width)

    def text(self) -> str:
        return "".join(_sgr(*style) + text for style, text in self.parts) + "\x1b[0m"


def _bar(state: State, width: int, now: float) -> Row:
    """Windows 95 blocks: each one a full cell and a half, so a thin gap shows between them."""
    row, units = Row(), width // 2
    if state.fraction is not None:
        full = round(max(0.0, min(1.0, state.fraction)) * units)
        lit = set(range(full))
        if now - state.changed > 4 and full < units and int(now * 2) % 2 == 0:
            lit.add(full)  # stalled (one big file, say): the next block blinks, so the step never looks stuck
    else:  # no known end: three blocks slide across
        at = int(now * 8) % (units + 3) - 3
        lit = {u for u in range(at, at + 3) if 0 <= u < units}
    for u in range(units):
        row.add("█▌", NAVY) if u in lit else row.add("  ")
    return row.fill(width)


def _step_rows(state: State, count: int, width: int, now: float) -> list[Row]:
    n = len(state.steps)
    start = max(0, min(state.current - count // 2, n - count)) if n > count else 0
    rows = []
    for i in range(start, min(n, start + count)):
        row, how = Row(), state.status[i]
        if count >= 3 and ((i == start and start > 0) or (i == start + count - 1 and start + count < n)):
            text = f"     … {start + 1} earlier" if i == start else f"     … {n - start - count + 1} more"
            rows.append(row.add(_fit(text, width), MUTED))
            continue
        mark, fg, bold, right = {"done": ("√", BLACK, False, elapsed(state.seconds[i] or 0)),
                                 "skip": ("√", MUTED, False, "already there"),
                                 "run": ("►", BLACK, True, elapsed(now - state.step_started)),
                                 "fail": ("×", RED, True, "failed")}.get(state.status[i], (" ", MUTED, False, ""))
        label_width = width - 6 - len(right) - 2
        row.add("   ").add(mark, fg, bold=bold).add(" ").add(_fit(state.steps[i], label_width), fg if how != "done" else BLACK, bold=bold)
        row.add(" " + right.rjust(width - row.width - 2) + " ", MUTED if how != "run" else BLACK)
        rows.append(row)
    return rows


def window_rows(state: State, width: int, height_left: int, now: float) -> list[Row]:
    """The window, `width` cells wide, made to fit in `height_left` lines when it can."""
    inner = width - 2
    group = inner - 4                 # the "Now" box inside the window
    fixed = 15                        # every line that is not an info line or a step
    info = list(state.info)
    steps_room = height_left - fixed - len(info)
    if steps_room < min(len(state.steps), 3):
        info, steps_room = [], height_left - fixed
    steps_room = max(1, min(len(state.steps), steps_room))

    def face_row(text="", fg=BLACK, bold=False) -> Row:
        return Row().add("│", LIGHT).add(_fit("  " + text, inner), fg, bold=bold).add("│", DARK)

    rows = [Row().add("┌" + "─" * inner, LIGHT).add("┐", DARK)]
    title = Row().add("│", LIGHT)
    buttons = inner >= 34
    title.add(_fit(" ■ " + TITLE, inner - (11 if buttons else 0)), LIGHT, NAVY, bold=True)
    if buttons:
        title.add(" _ ", BLACK, FACE).add(" □ ", BLACK, FACE).add(" ", NAVY, NAVY).add(" × ", BLACK, FACE, bold=True).add(" ", NAVY, NAVY)
    rows += [title.add("│", DARK), face_row()]
    rows += [face_row(line) for line in info] + ([face_row()] if info else [])
    for step in _step_rows(state, steps_room, inner, now):
        rows.append(Row().add("│", LIGHT).join(step).add("│", DARK))
    rows.append(face_row())

    def boxed(content: Row) -> Row:
        return Row().add("│", LIGHT).add("  ").add("│", DARK).join(content.cut(group - 2)).add("│", LIGHT).add("  ").add("│", DARK)

    label = " Setup is complete " if state.finished else " Now "
    rows.append(Row().add("│", LIGHT).add("  ").add("┌─", DARK).add(label).add("─" * (group - 2 - len(label) - 1) + "┐", DARK).add("  ").add("│", DARK))
    rows.append(boxed(Row().add(_fit(" " + (state.detail or "Starting"), group - 2))))
    rows.append(boxed(Row().add(" ").add("┌" + "─" * (group - 6), DARK).add("┐", LIGHT).add(" ").fill(group - 2)))
    rows.append(boxed(Row().add(" ").add("│", DARK).join(_bar(state, group - 6, now)).add("│", LIGHT).add(" ").fill(group - 2)))
    rows.append(boxed(Row().add(" ").add("└", DARK).add("─" * (group - 6) + "┘", LIGHT).add(" ").fill(group - 2)))
    if state.fraction is not None:
        left = f" {int(state.fraction * 100)}%"
    else:
        left = " Working" + "." * (int(now * 2) % 4)
    right = elapsed(now - state.step_started) + " " if state.current >= 0 and not state.finished else ""
    rows.append(boxed(Row().add(left.ljust(group - 2 - len(right)) + right)))
    rows.append(Row().add("│", LIGHT).add("  ").add("└" + "─" * (group - 2) + "┘", LIGHT).add("  ").add("│", DARK))
    rows.append(face_row())

    done = sum(1 for s in state.status if s in ("done", "skip"))
    at = min(len(state.steps), done + (0 if state.finished else 1))
    status = Row().add(" ")
    for i, piece in enumerate([f"Step {at} of {len(state.steps)}", f"Total {elapsed(now - state.started)}",
                               f"Log: {state.log_path}"]):
        if i:
            status.add(" │ ", DARK)
        status.add(piece)
    rows.append(Row().add("│", LIGHT).join(status.cut(inner)).add("│", DARK))
    rows.append(Row().add("└" + "─" * inner + "┘", DARK))
    return rows


def _taskbar(cols: int) -> Row:
    row = Row().add(" ").add(" ▓ Start ", BLACK, FACE, bold=True).add(" ", DARK).add(" ")
    clock = " " + datetime.datetime.now().strftime("%H:%M") + " "
    button = cols - row.width - len(clock) - 3
    if button > 8:
        row.add(_fit(" ■ " + TITLE, min(button, 34)), BLACK, PRESSED, bold=True)
    row.fill(cols - len(clock) - 1)
    return row.add(clock, BLACK, PRESSED).cut(cols)


def frame(state: State, cols: int, rows: int, now: float) -> list[str]:
    """The whole screen: `rows` lines `cols` wide, the last one a cell short (writing that cell scrolls)."""
    margin = cols >= 44 and rows >= 20
    width = min(cols - 4, 88) if margin else cols
    window = window_rows(state, width, rows - (4 if margin else 1), now)
    height = len(window)
    x0 = (cols - width - 1) // 2 if margin else 0
    y0 = max(1, (rows - 1 - height - 1) // 2) if margin else 0
    out = []
    for r in range(rows - 1):
        row = Row()
        if y0 <= r < y0 + height:
            row.add(" " * x0, TEAL, TEAL).join(window[r - y0].cut(min(width, cols - x0)))
            if margin:
                row.add(" ", BLACK, BLACK if r > y0 else TEAL)  # the window's shadow
        elif margin and r == y0 + height:
            row.add(" " * (x0 + 1), TEAL, TEAL).add(" " * width, BLACK, BLACK)
        out.append(row.fill(cols, TEAL).cut(cols).text())
    out.append(_taskbar(cols - 1).text())
    return out


# ---- the window --------------------------------------------------------------------------------------

def console_ready(out=None) -> bool:
    """Whether the window can be drawn: a real console that understands colours and cursor moves."""
    out = out or sys.stdout
    if os.environ.get("RACCONTAMI_PLAIN") or not hasattr(out, "isatty") or not out.isatty():
        return False
    cols, rows = shutil.get_terminal_size((0, 0))
    if cols < 40 or rows < 12:
        return False
    if sys.platform != "win32":
        return os.environ.get("TERM", "") not in ("", "dumb")
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.windll.kernel32
    handle, mode = kernel.GetStdHandle(-11), wintypes.DWORD()
    return bool(kernel.GetConsoleMode(handle, ctypes.byref(mode)) and kernel.SetConsoleMode(handle, mode.value | 0x0004))


class Screen:
    """The setup window for a list of steps. Plain lines instead when the output is not a console."""

    def __init__(self, info, labels, log_path, fancy: bool | None = None, out=None):
        self.out = out or sys.stdout
        self.state = State(list(info), list(labels), str(log_path), started=time.monotonic())
        self.fancy = console_ready(self.out) if fancy is None else fancy
        self.log = open(log_path, "a", encoding="utf-8")
        self.tail: collections.deque = collections.deque(maxlen=40)
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread: threading.Thread | None = None

    # the steps tell it what happens
    def __enter__(self) -> Screen:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._log(f"\n==== {TITLE}, {stamp}\n" + "\n".join(self.state.info))
        if self.fancy:
            self._write("\x1b[?1049h\x1b[?25l")
            self._open()
            self.thread = threading.Thread(target=self._tick, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def begin(self, i: int, detail: str = "Starting") -> None:
        with self.lock:
            s = self.state
            s.current, s.step_started, s.detail, s.fraction = i, time.monotonic(), detail, None
            s.changed = s.step_started
            s.status[i] = "run"
        self.tail.clear()
        self._log(f"\n== {self.state.steps[i]}")
        if not self.fancy:
            self._say(f"\n== {self.state.steps[i]}")

    def feed(self, line: str) -> None:
        line = visible(line).rstrip()
        if not line.strip():
            return
        update = read(line)
        kept = line if update is None or update.log else update.extra
        if kept:
            self._log(kept)
            self.tail.append(kept)
            if not self.fancy:
                self._say(kept)
        if update is not None:
            with self.lock:
                s, before = self.state, self.state.fraction
                if update.detail is not None:
                    s.detail, s.fraction = update.detail, update.fraction
                elif update.fraction is not None:
                    s.fraction = update.fraction
                if s.fraction != before:
                    s.changed = time.monotonic()

    def end(self, i: int, how: str) -> None:
        """how: done, skip (it was already there) or fail."""
        with self.lock:
            self.state.status[i] = how
            self.state.seconds[i] = time.monotonic() - self.state.step_started
            spent = self.state.seconds[i]
        self._log({"done": f"-- done in {elapsed(spent)}", "skip": "-- already there", "fail": "-- failed"}[how])
        if how == "skip" and not self.fancy:
            self._say("already there")

    def finish(self, linger: float = 1.5) -> None:
        with self.lock:
            self.state.finished, self.state.detail, self.state.fraction = True, "Everything is installed.", 1.0
        self._log(f"==== done in {elapsed(time.monotonic() - self.state.started)}")
        if self.fancy:
            time.sleep(linger)

    def close(self) -> None:
        """Gives the console back as it was: always runs, also after Ctrl+C or an error."""
        if self.thread:
            self.stopping.set()
            self.thread.join(timeout=2)
            self.thread = None
        if self.fancy:
            self._write("\x1b[0m\x1b[?25h\x1b[?1049l")
            self.fancy = False
        if not self.log.closed:
            self.log.close()

    def last_lines(self) -> list[str]:
        return list(self.tail)

    # drawing
    def _tick(self) -> None:
        while not self.stopping.is_set():
            self._draw()
            self.stopping.wait(0.125)

    def _draw(self) -> None:
        cols, rows = shutil.get_terminal_size((80, 25))
        with self.lock:
            lines = frame(self.state, cols, rows, time.monotonic())
        self._write("\x1b[H" + "\r\n".join(lines))

    def _open(self) -> None:
        """The window opens as Windows 95 drew it: outlines growing out of the taskbar button."""
        cols, rows = shutil.get_terminal_size((80, 25))
        final = len(window_rows(self.state, min(cols - 4, 88), rows - 4, 0.0))
        width = min(cols - 4, 88)
        x1, y1 = (cols - width - 1) // 2, max(1, (rows - 1 - final - 1) // 2)
        x0, y0, w0, h0 = 12, rows - 2, 20, 1
        for k in range(1, 7):
            t = k / 6
            x, y = round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t)
            w, h = round(w0 + (width - w0) * t), max(2, round(h0 + (final - h0) * t))
            screen = []
            for r in range(rows - 1):
                row = Row().add(" " * x, TEAL, TEAL)
                if r in (y, y + h - 1) and w > 1:
                    row.add(("┌" if r == y else "└") + "─" * (w - 2) + ("┐" if r == y else "┘"), FACE, TEAL)
                elif y < r < y + h - 1:
                    row.add("│", FACE, TEAL).add(" " * (w - 2), TEAL, TEAL).add("│", FACE, TEAL)
                screen.append(row.fill(cols, TEAL).cut(cols).text())
            screen.append(_taskbar(cols - 1).text())
            self._write("\x1b[H" + "\r\n".join(screen))
            time.sleep(0.035)

    def _write(self, text: str) -> None:
        try:
            self.out.write(text)
            self.out.flush()
        except (OSError, ValueError):  # the window was closed
            pass

    def _say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def _log(self, text: str) -> None:
        if not self.log.closed:
            self.log.write(text + "\n")
            self.log.flush()


def run(argv, env, screen: Screen) -> int:
    """Runs one step, its output (errors too) read line by line into the window and the log."""
    with subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, bufsize=0) as p:
        rest = b""
        try:
            while True:
                chunk = p.stdout.read(65536)
                if not chunk:
                    break
                lines, rest = split_lines(rest + chunk)
                for line in lines:
                    screen.feed(line)
            if rest:
                screen.feed(rest.decode("utf-8", "replace"))
            return p.wait()
        except BaseException:  # Ctrl+C, or the window closing: the step does not go on alone
            p.kill()
            raise


# ---- the demo: fake steps, to see the window without installing anything ------------------------------

_PIP = r"""
import sys, time
for name in ("torch==2.11.0", "sympy>=1.13.3 (from torch==2.11.0)", "networkx>=2.5.1 (from torch==2.11.0)"):
    print("Collecting " + name, flush=True); time.sleep(0.6)
print("Downloading https://download-r2.pytorch.org/whl/cu128/torch-2.11.0%2Bcu128-cp312-cp312-win_amd64.whl (2.9 GB)", flush=True)
total = 2900000000
for i in range(0, 101, 2):
    print(f"Progress {total * i // 100} of {total}", flush=True); time.sleep(0.12)
print("Installing collected packages: mpmath, typing-extensions, sympy, networkx, torch", flush=True)
time.sleep(5)
print("Successfully installed mpmath-1.3.0 sympy-1.14.0 torch-2.11.0+cu128", flush=True)
"""
_MODELS = r"""
import sys, time
for n, repo in enumerate(("facebook/wav2vec2-base-960h", "openbmb/VoxCPM2"), 1):
    print(f"model {n} of 3: {repo}", flush=True)
    for i in range(0, 11):
        sys.stderr.write(f"\rFetching 10 files: {i * 10:3d}%|{'#' * i:<10}| {i}/10 [00:01<00:00]"); sys.stderr.flush(); time.sleep(0.3)
    sys.stderr.write("\n")
print("model 3 of 3: whisper turbo", flush=True)
for i in range(0, 101, 4):
    sys.stderr.write(f"\r{i:3d}%|{'#' * (i // 10):<10}| {i * 15}M/1.51G [00:10<00:20]"); sys.stderr.flush(); time.sleep(0.08)
print("\nall models ready", flush=True)
"""
_NARRATOR = r"""
import time
print("Making a narrator for Turkish (a few minutes the first time)...", flush=True); time.sleep(5)
print("Narrator saved: C:\\Users\\you\\raccontami\\server-data\\narrators\\voxcpm2_tr_ref.wav (12.4 s)", flush=True)
"""
_FAIL = r"""
import sys, time
print("Collecting voxcpm==1.9", flush=True); time.sleep(1)
print("ERROR: Could not find a version that satisfies the requirement voxcpm==1.9", flush=True)
sys.exit(1)
"""


def demo(fail: bool) -> int:
    import tempfile
    steps = [("Python environment: server", "import time; time.sleep(1.5)", False),
             ("PyTorch with CUDA for the server (about 3 GB the first time)", _PIP, False),
             ("PyTorch with CUDA for the voice VoxCPM2 (about 3 GB the first time)", "", True),
             ("The other packages for the server (a few minutes)", "import time; time.sleep(4)", False),
             ("The models for English, Italian, Turkish", _MODELS, False),
             ("A narrator for Turkish", _NARRATOR, False)]
    if fail:
        steps.insert(4, ("The other packages for the voice VoxCPM2 (a few minutes)", _FAIL, False))
    log = os.path.join(tempfile.gettempdir(), "raccontami-setup-demo-log.txt")
    info = ["Installing to C:\\Users\\you\\raccontami", "Languages: English, Italian, Turkish   Port: 8765"]
    with Screen(info, [s[0] for s in steps], log) as screen:
        for i, (label, code, there) in enumerate(steps):
            screen.begin(i, "Checking what is already there" if there else "Starting")
            if there:
                time.sleep(1.2)
                screen.end(i, "skip")
                continue
            if run([sys.executable, "-u", "-c", code], dict(os.environ, PYTHONUNBUFFERED="1"), screen):
                screen.end(i, "fail")
                time.sleep(1)
                screen.close()
                print(f"This step failed: {label}\nIts last lines:\n" + "\n".join("  " + x for x in screen.last_lines()))
                print(f"\nThe whole output is in {log}")
                return 1
            screen.end(i, "done")
        screen.finish()
    print("Done (demo: nothing was installed).")
    return 0


if __name__ == "__main__":
    if "--demo" in sys.argv:
        sys.exit(demo("--fail" in sys.argv))
    print(__doc__)
