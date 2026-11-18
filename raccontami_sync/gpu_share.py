"""How much of the graphics card the server's work may take, so the computer stays usable.

There is no way on Windows to give a CUDA program "at most half of the card". The work paces
itself instead: after each step (a window of audio for Whisper or the aligner, a piece for a
voice) it pauses, so its working time stays at the share. 50 % means: after 2 s of work, 2 s of
rest. Each step still runs at full speed; the pauses leave the card to everything else, and the
jobs take longer in the same proportion. The memory the models take stays the same.

The share is in <data>/gpu-share.txt, a number from 10 to 100. The setting RACCONTAMI_GPU_SHARE
writes it at each start, and the server's page changes it while jobs run. Every step reads it,
so a change applies at once, also in a narration's voice, which runs in a Python of its own.
That is why this file uses only the standard library: the narration worker loads it from this
folder without the rest of the package.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

FILE = "gpu-share.txt"
LOWEST = 10         # %: below this a book would take days
MAX_PAUSE_S = 30.0  # one pause at most, whatever a step took


def parse(text: str) -> int | None:
    """A share from a setting or the file: a whole number, a % sign allowed, kept within LOWEST
    and 100. None when it is not a number."""
    try:
        share = int(text.strip().rstrip("%").strip())
    except ValueError:
        return None
    return max(LOWEST, min(100, share))


def read(path: Path) -> int:
    """The share in the file; full when there is none or it cannot be read."""
    try:
        return parse(path.read_text(encoding="utf-8")) or 100
    except OSError:
        return 100


def write(path: Path, share: int) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(f"{share}\n", encoding="utf-8")
    os.replace(tmp, path)  # a step reading it never sees half a file


class Pacer:
    """Call step() after each step of GPU work: it pauses for as long as the share asks.
    The time since the last step (or since the pacer was made) counts as work."""

    def __init__(self, share: Callable[[], int], clock=time.monotonic, sleep=time.sleep):
        self.share, self.clock, self.sleep = share, clock, sleep
        self.mark = clock()

    def step(self) -> None:
        worked = self.clock() - self.mark
        share = self.share()
        if share < 100 and worked > 0:
            self.sleep(min(MAX_PAUSE_S, worked * (100 - share) / share))
        self.mark = self.clock()
