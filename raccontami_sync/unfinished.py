"""Unfinished jobs, asked about when the server starts in a window.

A job is unfinished when it was waiting or running at the last stop, when it was put on hold at an
earlier start, or when it is a narration that stopped with an error and has finished pieces on disk
(closing the server's window in the middle of a narration ends that way).

With somebody at the keyboard the server asks, for each one: continue now? If not: delete the work
done so far? If not either, the job is on hold: it stays on disk, nothing works on it, and the
question comes back at every start until it is continued or deleted.

With nobody to ask (a service, Docker, no console) nothing changes from before: waiting and running
jobs continue, a failed narration stays failed until the phone sends it again, a job on hold stays so.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

CONTINUE, HOLD, DELETE, LEAVE = "continue", "hold", "delete", "leave"
HELD = "held"  # the state of a job on hold, in status.json and for the phone

YES = ("y", "yes", "s", "si", "sì")  # also Italian: the question is in English, the habit may not be
NO = ("n", "no")


def pieces_done(job: Path) -> int:
    d = job / "pieces"
    return sum(1 for _ in d.glob("*.wav")) if d.is_dir() else 0


def is_unfinished(job: Path, status: dict) -> bool:
    state = status.get("state")
    if state in ("queued", "running", HELD):
        return True
    return state == "failed" and status.get("kind") == "narrate" and pieces_done(job) > 0


def default_choice(status: dict) -> str:
    """What happens to an unfinished job when there is nobody to ask: what happened before the question existed."""
    return CONTINUE if status.get("state") in ("queued", "running") else LEAVE


def interactive(stdin=None, stdout=None) -> bool:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    try:
        return bool(stdin and stdout and stdin.isatty() and stdout.isatty())
    except (AttributeError, ValueError):  # no console at all, or a closed one
        return False


def _hm(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60} min" if seconds < 3600 else f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"


def describe(job: Path, status: dict) -> list[str]:
    """A few lines that let the reader recognise the job: the server knows no titles, so a narration
    is told by its language, its length and its first words."""
    kind = status.get("kind", "sync")
    percent = f"{int(float(status.get('progress') or 0) * 100)} % done"
    try:
        meta = json.loads((job / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    tokens = meta.get("tokens") if isinstance(meta.get("tokens"), list) else []
    lang = {"en": "English", "it": "Italian"}.get(meta.get("lang"), meta.get("lang") or "unknown language")
    try:
        last = time.strftime("%d %b %H:%M", time.localtime((job / "status.json").stat().st_mtime))
    except OSError:
        last = "unknown"
    state = status.get("state")
    how = {"failed": "It stopped with an error (closing the server's window while it works does that).",
           HELD: "It was put on hold at an earlier start.",
           "queued": "It was waiting for its turn."}.get(state, "It was being worked on when the server stopped.")
    if kind == "narrate":
        start = meta.get("start") if isinstance(meta.get("start"), int) else 0
        first = " ".join(str(t) for t in tokens[start:start + 8])
        lines = [f"A narration, {lang}, {len(tokens):,} words (about {_hm(len(tokens) / 2.5)} of audio)"
                 + (f', beginning "{first} ..."' if first else "")]
        done = pieces_done(job)
        lines.append(f"{percent}" + (f", {done:,} pieces of audio already made" if done else "") + f". Last worked on: {last}.")
    else:
        lines = [f"A sync of an audiobook with its text, {lang}, {len(tokens):,} words",
                 f"Last worked on: {last}. A sync starts again from the beginning (what was heard so far is kept)."]
    lines.append(how)
    return lines


def _yes_no(ask, question: str, default: bool) -> bool:
    """Asks until the answer is a yes or a no; Enter alone takes the default."""
    while True:
        answer = ask(f"{question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
        if not answer:
            return default
        if answer in YES:
            return True
        if answer in NO:
            return False


def choose(found: list[tuple[Path, dict]], ask=input, say=print) -> dict[str, str]:
    """Asks about each unfinished job and returns job folder name -> CONTINUE, HOLD or DELETE.
    When the answers end (the window has no keyboard after all), the rest gets what it got before the
    question existed, and nothing is deleted."""
    choices: dict[str, str] = {}
    say("")
    say(f"  Unfinished work was found: {len(found)} job(s).")
    for job, status in found:
        say("")
        for line in describe(job, status):
            say("    " + line)
        try:
            go = _yes_no(ask, "  Continue it now?", default=True)
        except EOFError:
            choices[job.name] = default_choice(status)
            continue
        if go:
            choices[job.name] = CONTINUE
            continue
        try:
            delete = _yes_no(ask, "  Delete the work done so far? This cannot be undone.", default=False)
        except EOFError:
            delete = False  # "do not continue" was said: the work is kept and not started
        choices[job.name] = DELETE if delete else HOLD
        if not delete:
            say("  Kept, on hold: nothing works on it, and you will be asked again at the next start.")
    say("")
    return choices
