"""Small JSON files that record a job's state (status.json, release.json).

They are read again when the server starts, so a file cut short by a power cut
must never stop the server: writes go to a temporary file that is then renamed,
and a file that cannot be read counts as missing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def write_json(path: Path, data) -> None:
    """Replaces [path] in one step: the old content stays until the new one is complete."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path):
    """The file's content, or None when it is missing, empty or damaged."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
