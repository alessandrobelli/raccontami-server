"""Starts the server without a window (Windows):

    pythonw -m raccontami_sync.background [--home DIR] [--host ADDRESS] [--port N]

The server then lives next to the clock: its icon says what it does, opens its page, puts the work
on hold and stops it. There is no window to close by mistake in the middle of a narration.

How: the real server is started as a separate process with a console that is never shown. It needs a
console, shown or not: the voice, ffmpeg and the libraries that call them are console programs, and
each would open a window of its own without one. What the window would show goes to
<data>/window.log. This starter waits a little, and if the server ends at once (it is already
running, the port is taken, something is not installed) it says so in a message box: a double click
that does nothing would be worse than a window.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

LOG = "window.log"
KEEP = 1_000_000  # bytes of an old log worth keeping


def failure_text(log_text: str) -> str:
    """What to tell the reader when the server ended at once: its own explanation when it gave one."""
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    for line in reversed(lines):
        if "NOT STARTED:" in line:
            return line.split("NOT STARTED:", 1)[1].strip()
    for line in reversed(lines):
        if "address already in use" in line.lower() or "10048" in line:
            return "Its port is already in use: the server may be running already (look for its icon next to the clock)."
    tail = "\n".join(lines[-6:]) or "It left no explanation."
    return "The server stopped right after starting.\n\n" + tail


def command(python: Path) -> list[str]:
    """The same start as in a window (serve.py: the encrypted link); address and port go by RACCONTAMI_HOST/PORT."""
    return [str(python), "-m", "raccontami_sync.serve"]


def _tell(text: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "Raccontami server", 0x10)  # an error box with OK
    except Exception:  # noqa: BLE001  no desktop: the log has it
        pass


def main(argv=None, wait: float = 40.0, tell=_tell) -> int:
    p = argparse.ArgumentParser(prog="raccontami_sync.background")
    p.add_argument("--home")
    p.add_argument("--host", default=os.environ.get("RACCONTAMI_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("RACCONTAMI_PORT", "8765")))
    a = p.parse_args(argv)
    if a.home:
        os.environ["RACCONTAMI_HOME"] = a.home
    os.environ.update(RACCONTAMI_WINDOWLESS="1", RACCONTAMI_HOST=a.host, RACCONTAMI_PORT=str(a.port),
                      PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    from .paths import DATA  # after the settings above: it reads them

    DATA.mkdir(parents=True, exist_ok=True)
    log = DATA / LOG
    if log.exists() and log.stat().st_size > KEEP:
        log.write_bytes(log.read_bytes()[-KEEP // 2:])
    start = log.stat().st_size if log.exists() else 0
    python = Path(sys.executable).with_name("python.exe" if os.name == "nt" else "python")
    with open(log, "ab") as out:
        proc = subprocess.Popen(command(python), cwd=Path(__file__).resolve().parent.parent,
                                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        code = proc.wait(timeout=wait)
    except subprocess.TimeoutExpired:
        return 0  # still running after the time a failed start takes: it is up
    with open(log, "rb") as f:
        f.seek(start)
        said = f.read().decode("utf-8", errors="replace")
    tell(failure_text(said))
    return code or 1


if __name__ == "__main__":
    sys.exit(main())
