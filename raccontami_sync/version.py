"""The server's version. It is written once, in version.json at the top of the repository: the
server reads it from there, and so does the "Check for a newer version" button of its page, which
compares it with the same file on GitHub."""

from __future__ import annotations

import json
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "version.json"
# where the page looks for the latest one; nothing is asked there unless the button is pressed
LATEST = "https://raw.githubusercontent.com/alessandrobelli/raccontami-server/main/version.json"


def read(file: Path = FILE) -> str:
    try:
        return str(json.loads(file.read_text(encoding="utf-8"))["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return "0"  # a copy without the file still starts; the page then cannot compare, and says so


VERSION = read()
