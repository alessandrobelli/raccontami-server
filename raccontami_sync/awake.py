"""Keeps the computer from going to sleep by itself while a job runs (Windows).

A narration takes hours and nobody touches the keyboard meanwhile, so Windows would put the
computer to sleep in the middle of it. While a job runs the server tells Windows it is busy; when
the job ends, is put on hold or fails, the computer sleeps as usual again. The screen may still turn
off, and closing a laptop's lid or pressing the power button still puts it to sleep (Windows does
not let a program prevent that).

RACCONTAMI_KEEP_AWAKE=0 switches it off. On Linux this does nothing: a server there is usually a
machine that does not sleep.

Windows keeps this per thread, so it is asked for and given back by the thread that does the work:
https://learn.microsoft.com/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager

OFF = ("0", "off", "no", "false")
ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


def wanted(platform=None, env=None) -> bool:
    platform, env = sys.platform if platform is None else platform, os.environ if env is None else env
    return platform == "win32" and env.get("RACCONTAMI_KEEP_AWAKE", "1").strip().lower() not in OFF


def _set(flags: int) -> None:
    import ctypes

    ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))


@contextmanager
def while_working(set_state=None):
    """For the time of the block, this thread asks Windows not to sleep. Never raises: a computer
    that falls asleep pauses the job, it does not break it."""
    if not wanted():
        yield
        return
    set_state = set_state or _set
    try:
        set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:  # noqa: BLE001  no such call on this Windows: the job matters more
        yield
        return
    try:
        yield
    finally:
        try:
            set_state(ES_CONTINUOUS)
        except Exception:  # noqa: BLE001
            pass
