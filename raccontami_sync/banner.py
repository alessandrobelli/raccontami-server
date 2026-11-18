"""The block the server prints when it starts: what it is, how to connect the phone, which models.

Plain ASCII rules and two columns, so it reads the same in the window, in server.log and in a
terminal over SSH. Every line starts under the time in front of the log lines (app.log), so the
block stays apart from what is logged after it.
"""

from __future__ import annotations

import textwrap

INDENT = " " * 10  # "09:28:37  ": the time and two spaces
WIDTH = 96         # after the indent: fits a window 110 characters wide (Windows Terminal opens at 120)
VALUE = 14         # where values start: two spaces, the name, the rest of its column

Row = tuple[str, str, str]  # name, value (several lines allowed), note ("" for none)


def render(sections: list[tuple[str, list[Row]]]) -> list[str]:
    """The block's lines, without line ends. A section without rows is left out."""
    shown = [(title, rows) for title, rows in sections if rows]
    out = []
    for i, (title, rows) in enumerate(shown):
        out.append(INDENT + ("=" if i == 0 else "-") * WIDTH)
        out.append(INDENT + title)
        for name, value, note in rows:
            first, *more = value.split("\n")
            out.append(INDENT + f"  {name:<{VALUE - 3}} {first}")
            out += [INDENT + " " * VALUE + line for line in more]
            out += [INDENT + " " * VALUE + line for line in textwrap.wrap(note, WIDTH - VALUE)]
    out.append(INDENT + "=" * WIDTH)
    return out
