"""Where the reader is in each book, so another phone or tablet can continue there.

A device tells the server "in book K I am at word N, as of time T"; another device asks for
book K and gets the newest answer. The book is named by a key the app computes from its text,
so the same book on two devices has the same key without the server knowing the book.
The position is a word of the text, not a time in the audio: each device finds the moment in
its own audio, and a story without audio works too.

Everything is one small JSON file in the data folder, written whole each time.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from .jsonfile import read_json, write_json

KEY = re.compile(r"^[0-9a-f]{16,64}$")
MAX_BOOKS = 2000  # the oldest are dropped beyond this
MAX_NAME = 60


class Positions:
    def __init__(self, file: Path):
        self.file = file
        self.lock = threading.Lock()
        data = read_json(file)
        self.books: dict[str, dict] = data if isinstance(data, dict) else {}

    def get(self, key: str) -> dict | None:
        with self.lock:
            return self.books.get(key)

    def put(self, key: str, token: int, at: int, device: str, name: str = "") -> dict:
        """Keeps the position if it is newer than the one known; returns the one kept."""
        with self.lock:
            known = self.books.get(key)
            if known is None or at > known.get("at", 0):
                self.books[key] = {"token": token, "at": at, "device": device, "name": name}
                if len(self.books) > MAX_BOOKS:
                    for old in sorted(self.books, key=lambda k: self.books[k].get("at", 0))[:len(self.books) - MAX_BOOKS]:
                        del self.books[old]
                write_json(self.file, self.books)
            return self.books[key]


def valid(key: str, body) -> tuple[int, int, str, str] | None:
    """(token, at, device, name) from a request, or None when it is not a position."""
    if not KEY.match(key) or not isinstance(body, dict):
        return None
    token, at, device, name = body.get("token"), body.get("at"), body.get("device"), body.get("name", "")
    numbers = all(isinstance(n, int) and not isinstance(n, bool) for n in (token, at))
    if not numbers or token < 0 or at <= 0:
        return None
    if not isinstance(device, str) or not 0 < len(device) <= MAX_NAME or not isinstance(name, str) or len(name) > MAX_NAME:
        return None
    return token, at, device, name
