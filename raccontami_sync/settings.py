"""The server's settings file: <home>/settings.txt.

One setting per line, NAME=value, with the names from the README (RACCONTAMI_ONE_JOB=1). Lines that
start with # are notes. The installers write the start files anew at every run, and the start
without a window does not go through a start file at all: settings written here are read by both,
and stay when the installer runs again.

What is already set where the server is started (a service file, docker run -e) wins over the file.
"""

from __future__ import annotations

import os
from pathlib import Path

FILE = "settings.txt"


def parse(text: str) -> dict[str, str]:
    """The settings in [text]. Only RACCONTAMI_ names: the file is not a way to change anything else."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = (part.strip() for part in line.split("=", 1))
        if name.startswith("RACCONTAMI_") and value:
            found[name] = value.strip('"')
    return found


def home(env=None) -> Path:
    """The home folder, worked out as paths.py does. Not imported from there: paths.py reads its
    settings when it is first imported, which must be after this file has been applied."""
    env = os.environ if env is None else env
    return Path(env.get("RACCONTAMI_HOME") or Path.home() / "raccontami").expanduser()


def load(env=None) -> list[str]:
    """Applies the file to [env] and returns the names it set. No file, or one that cannot be
    read, changes nothing: the server starts with its usual settings."""
    env = os.environ if env is None else env
    try:
        text = (home(env) / FILE).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []
    applied = []
    for name, value in parse(text).items():
        if name == "RACCONTAMI_HOME" or name in env:
            continue  # the file is found through the home folder; what the start set wins
        env[name] = value
        applied.append(name)
    return applied
