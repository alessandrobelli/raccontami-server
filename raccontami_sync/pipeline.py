"""Sync pipeline: audio + display tokens -> one time span per spoken token.

Stages and their share of the progress bar (measured in the Phase 0 spike on
an RTX 5080: Whisper ~85 % of the time, alignment ~13 %):
  decode 2 %  ->  transcribe 83 %  ->  match 1 %  ->  align 14 %
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import torch
import torchaudio.functional as AF

from .matcher import match
from .textnorm import norm_parts, strip_accents

SR = 16000
WHISPER_MODEL = "turbo"
ALIGN_MODELS = {
    "en": "facebook/wav2vec2-large-960h-lv60-self",
    "it": "jonatasgrosman/wav2vec2-large-xlsr-53-italian",
}
STAGES = [("decode", 0.02), ("transcribe", 0.83), ("match", 0.01), ("align", 0.14)]
WINDOW_S = 25.0

Progress = Callable[[str, float], None]  # (stage, fraction of that stage)


# ---------------------------------------------------------------- models

class Models:
    """Lazily loaded models, released after a period without jobs."""

    def __init__(self, cache_dir: Path, idle_unload_s: float = 600):
        self.cache_dir = cache_dir
        self.idle_unload_s = idle_unload_s
        self.lock = threading.Lock()
        self.whisper = None
        self.aligners: dict[str, "Aligner"] = {}
        self.last_used = time.monotonic()

    def get_whisper(self):
        import whisper

        if self.whisper is None:
            self.whisper = whisper.load_model(WHISPER_MODEL, device="cuda", download_root=str(self.cache_dir / "whisper"))
        self.last_used = time.monotonic()
        return self.whisper

    def get_aligner(self, lang: str) -> "Aligner":
        if lang not in self.aligners:
            self.aligners[lang] = Aligner(ALIGN_MODELS[lang])
        self.last_used = time.monotonic()
        return self.aligners[lang]

    def unload_if_idle(self):
        with self.lock:
            loaded = self.whisper is not None or self.aligners
            if loaded and time.monotonic() - self.last_used > self.idle_unload_s:
                self.whisper = None
                self.aligners.clear()
                torch.cuda.empty_cache()
                return True
        return False


class Aligner:
    def __init__(self, model_id: str):
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

        self.model_id = model_id
        self.proc = Wav2Vec2Processor.from_pretrained(model_id)
        self.model = Wav2Vec2ForCTC.from_pretrained(model_id).to("cuda").eval()
        self.vocab = self.proc.tokenizer.get_vocab()
        self.blank = self.proc.tokenizer.pad_token_id
        self.sep = self.vocab.get("|")

    def word_tokens(self, w: str) -> list[int]:
        out = []
        for c in w:
            for cand in (c, c.upper(), strip_accents(c), strip_accents(c).upper()):
                if cand in self.vocab:
                    out.append(self.vocab[cand])
                    break
        return out

    @torch.inference_mode()
    def emissions(self, wav: np.ndarray) -> torch.Tensor:
        x = self.proc(wav, sampling_rate=SR, return_tensors="pt").input_values.to("cuda")
        return torch.log_softmax(self.model(x).logits, dim=-1)

    def align(self, wav: np.ndarray, words: list[str]):
        """Word (start, end) in seconds relative to wav; None where unknown."""
        targets, owners = [], []
        for wi, w in enumerate(words):
            tk = self.word_tokens(w)
            if not tk:
                continue
            if self.sep is not None and targets:
                targets.append(self.sep)
                owners.append(-1)
            targets.extend(tk)
            owners.extend([wi] * len(tk))
        out = [None] * len(words)
        if not targets:
            return out
        em = self.emissions(wav)
        n_frames = em.shape[1]
        if len(targets) * 1.1 > n_frames:
            return out
        ali, scores = AF.forced_align(em, torch.tensor([targets], dtype=torch.int32, device=em.device), blank=self.blank)
        spans = AF.merge_tokens(ali[0], scores[0].exp())
        if len(spans) != len(targets):
            return out
        sec = len(wav) / SR / n_frames
        first: dict[int, int] = {}
        last: dict[int, int] = {}
        for k, o in enumerate(owners):
            if o >= 0:
                first.setdefault(o, k)
                last[o] = k
        for o in first:
            out[o] = (spans[first[o]].start * sec, spans[last[o]].end * sec)
        return out


# ---------------------------------------------------------------- stages

def decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def transcribe(models: Models, audio: np.ndarray, lang: str, progress: Progress):
    """Whisper with word timestamps; progress read from Whisper's own frame counter."""
    import sys

    import whisper  # noqa: F401  (loads the submodule)

    # whisper.transcribe is shadowed by the function of the same name; take the module
    wt = sys.modules["whisper.transcribe"]

    class _Bar:
        def __init__(self, total=None, **_):
            self.total, self.n = total or 1, 0

        def update(self, k):
            self.n += k
            progress("transcribe", min(1.0, self.n / self.total))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    original = wt.tqdm
    wt.tqdm = type("tqdm_shim", (), {"tqdm": _Bar})
    try:
        with models.lock:
            model = models.get_whisper()
            res = model.transcribe(audio, language=lang, word_timestamps=True,
                                   condition_on_previous_text=False, verbose=False)
    finally:
        wt.tqdm = original
    return [[w["word"].strip(), float(w["start"]), float(w["end"])]
            for seg in res["segments"] for w in seg.get("words", [])]


def fill_missing(times, spoken, words, lo_bound=0.0):
    """Interpolate None entries among spoken words by character length."""
    n = len(times)
    i = 0
    while i < n:
        if not spoken[i] or times[i] is not None:
            i += 1
            continue
        j = i
        while j < n and spoken[j] and times[j] is None:
            j += 1
        left = next((times[k][1] for k in range(i - 1, -1, -1) if spoken[k] and times[k] is not None), lo_bound)
        right = times[j][0] if j < n and spoken[j] and times[j] is not None else left + 0.35 * (j - i)
        total = sum(len(words[k]) + 1 for k in range(i, j))
        t, span = left, max(right - left, 0.0)
        for k in range(i, j):
            d = span * (len(words[k]) + 1) / total
            times[k] = (t, t + d)
            t += d
        i = j
    return times


@dataclass
class Result:
    language: str
    duration: float
    units: list = field(default_factory=list)       # [token, token, t0, t1] per spoken token
    audio_gaps: list = field(default_factory=list)  # {"t0","t1","excerpt"}
    text_gaps: list = field(default_factory=list)   # {"from","to"} token indexes never read aloud
    stats: dict = field(default_factory=dict)
    corrections: list = field(default_factory=list) # {"t": token, "w": spoken word} likely scan errors
    engine: dict | None = None                       # set for narrations: which voice made the audio

    def to_json(self) -> dict:
        return {
            "format": "raccontami-sync",
            "version": 3,
            "language": self.language,
            "duration": round(self.duration, 3),
            "engine": self.engine or {"anchors": f"whisper-{WHISPER_MODEL}", "align": ALIGN_MODELS[self.language]},
            "units": self.units,
            "audioGaps": self.audio_gaps,
            "textGaps": self.text_gaps,
            "corrections": self.corrections,
            "stats": self.stats,
        }


def run(models: Models, audio_path: Path, tokens: list[str], lang: str, progress: Progress,
        transcript_cache: Path | None = None) -> Result:
    import json

    progress("decode", 0.0)
    audio = decode(audio_path)
    duration = len(audio) / SR
    progress("decode", 1.0)

    # match words from display tokens
    A: list[str] = []
    owner: list[int] = []
    for d, tok in enumerate(tokens):
        for p in norm_parts(tok, lang):
            A.append(p)
            owner.append(d)

    if transcript_cache and transcript_cache.exists():
        words = json.loads(transcript_cache.read_text(encoding="utf-8"))
        progress("transcribe", 1.0)
    else:
        words = transcribe(models, audio, lang, progress)
        if transcript_cache:
            transcript_cache.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    B, Bt = [], []
    for w, t0, t1 in words:
        parts = norm_parts(w, lang)
        for k, p in enumerate(parts):
            d = (t1 - t0) / len(parts)
            B.append(p)
            Bt.append((t0 + k * d, t0 + (k + 1) * d))

    progress("match", 0.0)
    pairs = match(A, B)
    progress("match", 1.0)

    # gaps
    spoken = [True] * len(A)
    wtime = [None] * len(A)
    for i, j in pairs:
        wtime[i] = Bt[j]
    text_gap_ranges, audio_gaps, breaks = [], [], set()
    bounds = [(-1, -1)] + pairs + [(len(A), len(B))]
    for (i1, j1), (i2, j2) in zip(bounds, bounds[1:]):
        tr, br = i2 - i1 - 1, j2 - j1 - 1
        t_left = Bt[j1][1] if j1 >= 0 else 0.0
        t_right = Bt[j2][0] if j2 < len(B) else duration
        span = max(t_right - t_left, 0.0)
        text_only = tr >= 8 and span < 0.3 * tr
        if text_only:
            for k in range(i1 + 1, i2):
                spoken[k] = False
            text_gap_ranges.append((i1 + 1, i2 - 1))
            breaks.add(i2)
        spoken_text = 0 if text_only else tr
        by_words = br >= 6 and (text_only or br > 3 * tr)
        by_time = span > 4.0 + 0.6 * spoken_text
        if by_words or by_time:
            g0 = Bt[j1 + 1][0] if by_words else t_left
            g1 = Bt[j2 - 1][1] if by_words else t_right
            audio_gaps.append({"t0": round(g0, 2), "t1": round(g1, 2),
                               "excerpt": " ".join(w[0] for w in words if g0 <= w[1] < g1)[:120]})
            if not text_only and tr:
                for k in range(i1 + 1, i2):
                    spoken[k] = False
            breaks.add(i2)

    # alignment windows: cut between matched words, never across a gap
    windows = []
    cur_start = None
    matched_idx = [i for i, _ in pairs]
    for idx, i in enumerate(matched_idx):
        if cur_start is None or i in breaks:
            if windows:
                windows[-1]["end_i"] = matched_idx[idx - 1]
            windows.append({"start_i": i, "t0": max(0.0, wtime[i][0] - 0.3), "span_start": True})
            cur_start = wtime[i][0]
        elif wtime[i][0] - cur_start >= WINDOW_S and wtime[i - 1] is not None and spoken[i - 1]:
            windows[-1]["end_i"] = i - 1
            windows.append({"start_i": i, "t0": wtime[i][0] - 0.15, "span_start": False})
            cur_start = wtime[i][0]
    if windows:
        windows[-1]["end_i"] = matched_idx[-1]
    for k, w in enumerate(windows):
        nxt = windows[k + 1] if k + 1 < len(windows) else None
        w["t1"] = (wtime[nxt["start_i"]][0] + 0.05) if nxt is not None and not nxt["span_start"] \
            else min(duration, wtime[w["end_i"]][1] + 0.4)

    progress("align", 0.0)
    times = [None] * len(A)
    with models.lock:
        aligner = models.get_aligner(lang)
        for n, w in enumerate(windows):
            idxs = [k for k in range(w["start_i"], w["end_i"] + 1) if spoken[k]]
            s0, s1 = int(w["t0"] * SR), int(w["t1"] * SR)
            for k, r in zip(idxs, aligner.align(audio[s0:s1], [A[k] for k in idxs])):
                if r is not None:
                    times[k] = (w["t0"] + r[0], w["t0"] + r[1])
            progress("align", (n + 1) / max(1, len(windows)))
    ctc_timed = sum(t is not None for t in times)
    times = fill_missing(times, spoken, A)

    # per display token
    n = len(tokens)
    t0s = [None] * n
    t1s = [None] * n
    for m, d in enumerate(owner):
        if spoken[m] and times[m] is not None:
            a, b = times[m]
            t0s[d] = a if t0s[d] is None else min(t0s[d], a)
            t1s[d] = b if t1s[d] is None else max(t1s[d], b)
    units = [[d, d, t0s[d], t1s[d]] for d in range(n) if t0s[d] is not None]
    for k in range(1, len(units)):
        if units[k][2] < units[k - 1][2]:
            units[k][2] = units[k - 1][3]
            units[k][3] = max(units[k][3], units[k][2] + 0.05)
    for k in range(len(units) - 1):
        if 0 < units[k + 1][2] - units[k][3] < 0.6:
            units[k][3] = units[k + 1][2]
    units = [[u[0], u[1], round(u[2], 3), round(u[3], 3)] for u in units]

    text_gaps = [{"from": owner[a], "to": owner[b]} for a, b in text_gap_ranges if a <= b]
    stats = {
        "audioSeconds": round(duration, 1),
        "matchWords": len(A),
        "transcriptWords": len(B),
        "matchedPct": round(100 * len(pairs) / max(1, sum(spoken)), 1),
        "ctcTimedPct": round(100 * ctc_timed / max(1, sum(spoken)), 1),
        "spokenTokens": len(units),
    }
    corrections = scan_corrections(A, B, owner, pairs, spoken, lang, tokens)
    stats["corrections"] = len(corrections)
    return Result(lang, duration, units, audio_gaps, text_gaps, stats, corrections)


# Letters a scanner confuses because they look alike (lowercase; capitals such as
# R/E, B/R, K/N, F/P show up here after lowercasing).
_CONFUSABLE = {frozenset(p) for p in (
    "rt", "ec", "eo", "co", "li", "fl", "ft", "tl", "hb", "hn", "nu", "uv", "re", "rb", "nk", "nx",
    "pf", "ao", "du", "jp", "ij", "gq", "mn", "ce", "il", "ri", "rn", "cg", "hk", "vy", "ui",
)}
_THIN = set("ilj1|!'.,")  # thin marks a scanner adds or drops


def _ocr_plausible(printed_token: str, a: str, b: str) -> bool:
    """True when turning a into b looks like fixing a scan error, not changing a word.

    Junk inside the printed word (i)ensare, piacer^) is enough on its own.
    Otherwise every edit must swap look-alike letters, drop or add a thin mark,
    or only change an accent.
    """
    import unicodedata

    from rapidfuzz.distance import Levenshtein

    core = printed_token.strip(".,;:!?\"'«»“”‘’()[]—–-")
    if any(not ch.isalpha() for ch in core):
        return True

    def base(ch):
        return unicodedata.normalize("NFD", ch)[0]

    for op in Levenshtein.editops(a, b):
        if op.tag == "replace":
            x, y = a[op.src_pos], b[op.dest_pos]
            if base(x) == base(y) or frozenset((base(x), base(y))) in _CONFUSABLE:
                continue
            return False
        ch = a[op.src_pos] if op.tag == "delete" else b[op.dest_pos]
        if ch not in _THIN:
            return False
    return True


def scan_corrections(A, B, owner, pairs, spoken, lang, tokens=None):
    """Likely recognition errors in a scanned text, with the word actually spoken.

    No dictionary: the book is its own. A text word is replaced only when it is
    rare in this book (<= 2 times) while the spoken word is common in it
    (>= 3 times), or appears up to 15 times while the spoken word is at least
    20 times more common, and the two are spelled almost alike. Real words that the
    narrator reads differently ("da" read as "di") are common, so they stay.
    A third rule uses a word list of the language (wordfreq): a printed word that
    appears once in the book and is not a word of the language at all, while the
    spoken word is ("gTattandosi" -> "grattandosi"). Old spellings the author
    uses on purpose ("maraviglia") are real words or recur, so they stay.
    Candidates come from matched pairs that differ and from 1:1 substitutions
    between two matched words. Only single-word tokens are considered.
    """
    from collections import Counter

    from rapidfuzz.distance import Levenshtein

    from wordfreq import zipf_frequency as zipf

    freq = Counter(A)
    parts = Counter(owner)
    out = {}

    def consider(i, j):
        a, b = A[i], B[j]
        if a == b or not spoken[i] or parts[owner[i]] != 1:
            return
        fa, fb = freq[a], freq.get(b, 0)
        rare = fa <= 2 and fb >= 3
        # a recognition error a scan repeats ("nna" for "una") is not rare, but
        # still dwarfed by the real word
        repeated_error = fa <= 15 and fb >= 20 * fa
        not_a_word = fa == 1 and zipf(a, lang) == 0 and zipf(b, lang) >= 1.0
        if not (rare or repeated_error or not_a_word) or not b.isalpha() or len(b) < 2:
            return
        if tokens is not None and not _ocr_plausible(tokens[owner[i]], a, b):
            return
        if Levenshtein.distance(a, b) > max(1, len(b) // 3):
            return
        out[owner[i]] = b

    for i, j in pairs:
        consider(i, j)
    for (i1, j1), (i2, j2) in zip(pairs, pairs[1:]):
        if i2 - i1 == 2 and j2 - j1 == 2:
            consider(i1 + 1, j1 + 1)
    return [{"t": t, "w": w} for t, w in sorted(out.items())]
