"""Normalization of display tokens into match words (shared rules with the app)."""

from __future__ import annotations

import re
import unicodedata

from num2words import num2words

_APOS = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'"})
_SPLIT = re.compile(r"[-‐-―_/]+")
_NONWORD = re.compile(r"[^\w]+", re.UNICODE)


def norm_parts(token: str, lang: str) -> list[str]:
    """One display token or ASR word -> zero or more lowercase match words.

    "l'amico" -> ["l", "amico"] (Italian), "don't" -> ["dont"] (English),
    "rose-tree" -> ["rose", "tree"], "1984" -> spelled out, "--" -> [].
    """
    s = unicodedata.normalize("NFKC", token).lower().translate(_APOS)
    s = s.replace("'", " ") if lang == "it" else s.replace("'", "")
    out: list[str] = []
    for piece in _SPLIT.sub(" ", s).split():
        piece = _NONWORD.sub("", piece).replace("_", "")
        if not piece:
            continue
        if piece.isdigit():
            try:
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
