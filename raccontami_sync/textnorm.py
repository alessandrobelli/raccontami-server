"""Normalization of display tokens into match words (shared rules with the app)."""

from __future__ import annotations

import re
import unicodedata

_APOS = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'"})
_SPLIT = re.compile(r"[-‐-―_/]+")
# languages where an apostrophe stands for a dropped vowel between two words ("l'amico", "l'homme")
_ELISION = {"it", "fr"}


def _keep(c: str) -> bool:
    """A letter, a digit, or a mark that belongs to the letter before it: the vowel signs of Hindi and other
    Indic scripts are such marks, and without them a word loses its vowels (हिंदी would become हद)."""
    return c.isalnum() or unicodedata.category(c) in ("Mn", "Mc")


def norm_parts(token: str, lang: str) -> list[str]:
    """One display token or ASR word -> zero or more lowercase match words.

    "l'amico" -> ["l", "amico"] (Italian, French), "don't" -> ["dont"] (English),
    "rose-tree" -> ["rose", "tree"], "1984" -> spelled out, "--" -> [].
    """
    s = unicodedata.normalize("NFKC", token).lower().translate(_APOS)
    s = s.replace("'", " ") if lang in _ELISION else s.replace("'", "")
    out: list[str] = []
    for piece in _SPLIT.sub(" ", s).split():
        piece = "".join(c for c in piece if _keep(c))
        if not piece:
            continue
        if piece.isdigit():
            try:
                from num2words import num2words  # only when there is a number: the GitHub check has no num2words

                spoken = num2words(int(piece), lang=lang)
            except Exception:
                out.append(piece)
                continue
            out.extend(norm_parts(spoken, lang))
        else:
            out.append(piece)
    return out


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
