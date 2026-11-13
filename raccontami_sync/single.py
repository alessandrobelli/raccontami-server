"""One server per data folder.

A second server started on the same folder would find the first one's running job "unfinished" and
ask about it, start it again beside the first, or delete it, all before noticing that the port is
taken (the port is opened last). So a start takes a lock in the data folder first and keeps it for
as long as it runs; the system drops it when the process ends, however it ends.
"""

from __future__ import annotations

import os
from pathlib import Path

NAME = "server.lock"


def take(data: Path):
    """The lock, to be kept (an open file), or None when another server already runs on this folder."""
    f = open(data / NAME, "a+b")
    try:
        if os.name == "nt":
            import msvcrt

            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f
