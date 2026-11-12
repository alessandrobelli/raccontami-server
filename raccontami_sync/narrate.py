"""Narration jobs: text in, audiobook + sync file out.

  1. plan     the book is cut into pieces: whole paragraphs, split at sentence
              ends only when a paragraph is long (reading whole paragraphs
              keeps the voice's tone; sentence by sentence sounds flatter).
  2. narrate  narrate_worker.py speaks each piece in the voice's own Python
              environment, at low priority, one WAV per piece. Pieces on disk
              are kept, so a restart continues where it stopped.
  3. align    each piece is aligned with its own words (wav2vec2 CTC, as in
              the audiobook sync) as soon as it is spoken. A piece whose words
              mostly do not align was probably misread: it is spoken again, once,
              after the rest.
  4. parts    while narrating, the finished beginning is published as numbered
              parts (10 min, 20, 40, 80 ...) so the phone can start listening early.
  5. encode   pieces + pauses -> one AAC file; word times are offset by where
              each piece lands, giving the usual sync file.
"""

from __future__ import annotations

import bisect
import json
import os
import re
import subprocess
import threading
import time
import wave
from pathlib import Path

import numpy as np

from . import paths
from .jsonfile import read_json, write_json
from .pipeline import ALIGN_MODELS, SR, Models, Progress, Result, fill_missing
from .textnorm import norm_parts

STAGES = [("narrate", 0.94), ("align", 0.04), ("encode", 0.02)]
VERSION = 2  # bump when a change should redo existing narrations
MAX_CHARS = 600  # a longer paragraph is split at sentence ends
PAUSE_PARAGRAPH = 0.85
PAUSE_SPLIT = 0.35
PAUSE_EMPTY = 1.0  # paragraphs with nothing to say, such as "* * *"
ALIGNED_ENOUGH = 0.7

from .paths import CACHE, MODELS, TTS, VOICES  # noqa: E402


def _python(env: str) -> str:
    """The Python of a voice environment under RACCONTAMI_TTS (Windows or Linux layout)."""
    win = TTS / env / "Scripts" / "python.exe"
    return str(win if os.name == "nt" else TTS / env / "bin" / "python")


VOICES = {
    "it": {"engine": "voxcpm2", "python": _python("env-a"),
           "voice": str(VOICES / "voxcpm2_it_ref.wav"), "label": "VoxCPM2 (Italian narrator)"},
    "en": {"engine": "qwen3", "python": _python("env-c"),
           "speaker": "aiden", "language": "English", "label": "Qwen3-TTS · Aiden"},
}


def voices(data: Path) -> dict:
    """Built-in voices, overridable per language in <data>/voices.json."""
    out = {k: dict(v) for k, v in VOICES.items()}
    f = data / "voices.json"
    if f.exists():
        for lang, v in json.loads(f.read_text(encoding="utf-8")).items():
            out.setdefault(lang, {}).update(v)
    return out


def voice_library(data: Path, lang: str) -> dict:
    """The voices a narrator can be given besides the language's own, by id.

    Each is a clip of a few seconds of clean speech: the .wav files in <repo>/voices/<lang>/ and in
    <data>/voices/<lang>/ (the file name without .wav is the id). A voices.json beside them may
    say more: {"<id>": {"label": "Anna", "gender": "f"}}. Only a voice that clones from a clip
    (VoxCPM2) can use them."""
    if voices(data).get(lang, {}).get("engine") != "voxcpm2":
        return {}
    out = {}
    # (the module's VOICES is the table of built-in voices; the folder of clips is paths.VOICES)
    for folder in (paths.VOICES / lang, data / "voices" / lang):
        if not folder.is_dir():
            continue
        info = read_json(folder / "voices.json")
        info = info if isinstance(info, dict) else {}
        for clip in sorted(folder.glob("*.wav")):
            more = info.get(clip.stem) if isinstance(info.get(clip.stem), dict) else {}
            out[clip.stem] = {"voice": str(clip), "label": str(more.get("label", clip.stem)),
                              "gender": more.get("gender") if more.get("gender") in ("f", "m") else None}
    return out


# ---------------------------------------------------------------- plan

_SENTENCE_END = re.compile(r"[.!?…]+[\"'»”’)\]]*$")
_CLAUSE_END = re.compile(r"[,;:—–]+[\"'»”’)\]]*$")
_ROMAN = re.compile(r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})([.:]?)$")
_CHAPTER_WORDS = {"capitolo", "chapter", "parte", "part", "libro", "book", "atto", "act", "canto"}


def _roman_value(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for a, b in zip(s, s[1:] + " "):
        v = vals[a]
        total += -v if b != " " and vals.get(b, 0) > v else v
    return total


def speakable(tokens: list[str]) -> str:
    """What the voice reads for a run of tokens: headings in capitals are
    lowered ("CAPITOLO XII" -> "Capitolo 12") so they are read as words."""
    out = []
    for k, t in enumerate(tokens):
        prev = re.sub(r"\W", "", tokens[k - 1]).lower() if k else ""
        m = _ROMAN.match(t)
        if m and prev in _CHAPTER_WORDS:
            out.append(str(_roman_value(t.rstrip(".:"))) + m.group(4))
        elif sum(c.isalpha() for c in t) > 1 and t.upper() == t:
            out.append(t.lower().capitalize() if k == 0 or out[-1].endswith((".", "!", "?")) else t.lower())
        else:
            out.append(t)
    text = " ".join(out)
    return text[0].upper() + text[1:] if text else text


def plan_pieces(tokens: list[str], paragraphs: list[int], start: int = 0, silent=(),
                narrators=(), cast=None) -> list[dict]:
    """Pieces as {"i", "from", "to" (inclusive token range), "say", "pause"}.

    The pieces before token [start] (the title page and index of a scan) are kept, so that
    token numbers stay the same, but they are not spoken and take no time.

    The tokens numbered in [silent] (the symbols that mark who narrates) are never spoken:
    they stay in their piece, so the reader still shows them, without a time.

    [narrators] says who tells the story from which token on, as [first token, name] in order,
    and [cast] which voice each name has. A piece never crosses a change of narrator, and one
    whose narrator has a voice carries it as "voice"; the others are read by the language's own."""
    silent = set(silent)
    changes = [int(first) for first, _name in narrators]
    # a change of narrator is a break like a new paragraph, also in the middle of one
    starts = sorted(set(p for p in list(paragraphs) + changes if 0 <= p < len(tokens)) | {0})
    bounds = list(zip(starts, starts[1:] + [len(tokens)]))
    pieces: list[dict] = []

    def add(a: int, b: int, pause: float):
        say = speakable([t for k, t in enumerate(tokens[a:b], a) if k not in silent])
        if b <= start:
            say, pause = "", 0.0
        elif not any(ch.isalnum() for ch in say):
            say, pause = "", PAUSE_EMPTY
        pieces.append({"i": len(pieces), "from": a, "to": b - 1, "say": say, "pause": pause})

    for a, b in bounds:
        if len(" ".join(tokens[a:b])) <= MAX_CHARS:
            add(a, b, PAUSE_PARAGRAPH)
            continue
        # split at sentence ends, then at clause ends, then anywhere
        # (not named "start": add() reads the parameter of that name)
        cuts, size = [], 0
        for k in range(a, b):
            size += len(tokens[k]) + 1
            if k + 1 == b:
                break
            # only the end of the word matters, and looking at the whole of a very long "word"
            # (a row of dots sent on purpose) would take hours and stall the server
            tail = tokens[k][-16:]
            if size >= MAX_CHARS * 0.5 and _SENTENCE_END.search(tail) or \
                    size >= MAX_CHARS * 0.85 and _CLAUSE_END.search(tail) or size >= MAX_CHARS:
                cuts.append(k + 1)
                size = 0
        edges = [a] + cuts + [b]
        for x, y in zip(edges, edges[1:]):
            add(x, y, PAUSE_PARAGRAPH if y == b else PAUSE_SPLIT)
    if cast and changes:
        for p in pieces:
            k = bisect.bisect_right(changes, p["from"]) - 1
            voice = cast.get(narrators[k][1]) if k >= 0 else None
            if voice:
                p["voice"] = voice
    return pieces


# ---------------------------------------------------------------- run

def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return pcm.astype(np.float32) / 32768.0, sr


def _to_16k(wav: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR:
        return wav
    import torch
    import torchaudio.functional as F

    return F.resample(torch.from_numpy(wav), sr, SR).numpy()


def _run_worker(job: Path, voice: dict, on_piece, stop, note=lambda msg: None) -> None:
    env = dict(os.environ)
    env.update({
        "PYTHONIOENCODING": "utf-8", "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2",
        "HF_HOME": env.get("HF_HOME", str(MODELS / "hf")),
        "TORCHINDUCTOR_CACHE_DIR": str(CACHE / "inductor"),
        "TRITON_CACHE_DIR": str(CACHE / "triton"),
    })
    flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)  # Windows: never slow the desktop down
    log = open(job / "narrate.log", "a", encoding="utf-8")
    proc = subprocess.Popen([voice["python"], "-u", str(Path(__file__).with_name("narrate_worker.py")), str(job)],
                            stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8", env=env,
                            creationflags=flags)

    def watch():
        # the voice prints nothing while it loads (minutes, the first time): a stop asked for then
        # must not wait for its next line
        while proc.poll() is None:
            if stop():
                proc.kill()
                return
            time.sleep(0.5)

    threading.Thread(target=watch, daemon=True).start()
    try:
        for line in proc.stdout:
            log.write(line)
            log.flush()
            if line.startswith("piece "):
                on_piece(int(line.split()[1]))
            elif line.startswith("ready"):
                note("voice ready, narrating")
            elif line.startswith("todo "):
                todo, _, of = line.split()[1:4]
                if todo != of:
                    note(f"resuming: {int(of) - int(todo)} of {of} pieces were already done")
            if stop():
                proc.kill()
                break
        proc.wait()
    finally:
        log.close()
    if proc.returncode not in (0, None) and not stop():
        tail = (job / "narrate.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-3:]
        raise RuntimeError("The voice stopped with an error: " + " | ".join(tail))


def _units(t0s, t1s):
    n = len(t0s)
    units = [[d, d, t0s[d], t1s[d]] for d in range(n) if t0s[d] is not None]
    for k in range(1, len(units)):
        if units[k][2] < units[k - 1][2]:
            units[k][2] = units[k - 1][3]
            units[k][3] = max(units[k][3], units[k][2] + 0.05)
    for k in range(len(units) - 1):
        if 0 < units[k + 1][2] - units[k][3] < 0.6:
            units[k][3] = units[k + 1][2]
    return [[u[0], u[1], round(u[2], 3), round(u[3], 3)] for u in units]


def first_release_seconds(expected_total: float) -> float:
    """Audio in the first part: 10 min, or a quarter of a shorter book (at least 30 s)."""
    cap = float(os.environ.get("RACCONTAMI_FIRST_PART_S", 600))
    return min(cap, max(30.0, expected_total / 4))


def release_threshold(release: int, first: float) -> float:
    """Audio length (s) the finished beginning must reach for part number [release] (1, 2, ...):
    the first part, then double each time. The voice runs ~3x faster than listening, so a listener
    who starts with part 1 does not catch up, and the downloads add up to at most ~2x the book."""
    return first * 2 ** (release - 1)


def last_release(job: Path) -> int:
    """Number of the latest part published for this job, 0 when there is none.

    The phone only takes a part with a higher number than the one it has, so this must
    never go back: when release.json cannot be read, the part files on disk tell it."""
    info = read_json(job / "release.json")
    if isinstance(info, dict) and isinstance(info.get("release"), int):
        return info["release"]
    numbers = [int(m.group(1)) for f in job.glob("partial-*.m4a") if (m := re.fullmatch(r"partial-(\d+)", f.stem))]
    return max(numbers, default=0)


def run(models: Models, job: Path, data: Path, progress: Progress, stop=lambda: False,
        on_release=lambda info: None, note=lambda msg: None) -> Result:
    """Narrates, aligns each piece as soon as it is spoken, and publishes the finished
    beginning of the book as numbered parts (partial-<n>.m4a + partial-<n>.json) so the
    phone can start listening early. [on_release] gets {"release", "audioSeconds", "toToken"}."""
    meta = json.loads((job / "meta.json").read_text(encoding="utf-8"))
    lang, tokens = meta["lang"], meta["tokens"]
    silent = set(meta.get("silent") or ())  # never spoken, so never timed
    voice = voices(data)[lang]
    plan_file = job / "plan.json"
    if plan_file.exists():
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
    else:
        # the cast is settled here, with the plan: a narration that is resumed keeps its voices
        library = voice_library(data, lang)
        cast = {name: v for name, v in (meta.get("cast") or {}).items() if v in library}
        plan = {"voice": voice, "voices": {v: library[v]["voice"] for v in sorted(set(cast.values()))},
                "pieces": plan_pieces(tokens, meta["paragraphs"], meta.get("start", 0), meta.get("silent", ()),
                                      meta.get("narrators") or (), cast)}
        plan_file.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    pieces = plan["pieces"]
    spoken = [p for p in pieces if p["say"]]
    by_index = {p["i"]: p for p in pieces}
    weight = {p["i"]: len(p["say"]) for p in spoken}
    total = max(1, sum(weight.values()))
    first = first_release_seconds(total / 14.0)  # speech is about 14 characters a second
    pdir = job / "pieces"
    pdir.mkdir(exist_ok=True)
    engine = {"tts": plan["voice"].get("label", plan["voice"]["engine"]), "align": ALIGN_MODELS[lang]}

    retried = set(json.loads((job / "retried.json").read_text()) if (job / "retried.json").exists() else [])
    times: dict[int, list] = {}  # piece -> [words, owner, spans, seconds]
    bad: set[int] = set()
    rel_file = job / "release.json"
    release = last_release(job)

    def wav_of(i):
        return pdir / f"{i:05d}.wav"

    def align(i):
        """Times one finished piece against its words; notes it when most words do not fit."""
        p = by_index[i]
        words, owner = [], []
        for d in range(p["from"], p["to"] + 1):
            if d in silent:
                continue
            for part in norm_parts(tokens[d], lang):
                words.append(part)
                owner.append(d)
        wav, sr = _read_wav(wav_of(i))
        with models.lock:
            r = models.get_aligner(lang).align(_to_16k(wav, sr), words) if words else []
        times[i] = [words, owner, list(r), len(wav) / sr]
        if words and sum(x is not None for x in r) < ALIGNED_ENOUGH * len(words) and i not in retried:
            bad.add(i)

    def build(upto: int, audio_out: Path):
        """Encodes pieces[:upto] with their pauses into audio_out; returns (t0s, t1s, seconds)."""
        rate = _read_wav(wav_of(spoken[0]["i"]))[1] if spoken else 24000
        tmp = audio_out.with_name(audio_out.stem + ".tmp.m4a")
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "-",
                                "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(tmp)],
                               stdin=subprocess.PIPE, creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        n = len(tokens)
        t0s: list = [None] * n
        t1s: list = [None] * n
        cursor = 0.0
        for k, p in enumerate(pieces[:upto]):
            if p["say"]:
                wav, sr = _read_wav(wav_of(p["i"]))
                if sr != rate:
                    raise RuntimeError("pieces have different sample rates; delete the job and start again")
                words, owner, r, dur = times[p["i"]]
                r = fill_missing(list(r), [True] * len(words), words)
                for (a, b), d in zip(r, owner):
                    a, b = min(a, dur), min(b, dur)
                    t0s[d] = cursor + a if t0s[d] is None else min(t0s[d], cursor + a)
                    t1s[d] = cursor + b if t1s[d] is None else max(t1s[d], cursor + b)
                enc.stdin.write((np.clip(wav, -1, 1) * 32767).astype("<i2").tobytes())
                cursor += len(wav) / rate
            enc.stdin.write(np.zeros(int(p["pause"] * rate), dtype="<i2").tobytes())
            cursor += int(p["pause"] * rate) / rate
            if upto == len(pieces):
                progress("encode", 0.9 * (k + 1) / len(pieces))
        enc.stdin.close()
        if enc.wait() != 0:
            raise RuntimeError("ffmpeg could not write the audio file")
        os.replace(tmp, audio_out)
        return t0s, t1s, cursor

    def ready_prefix():
        """(pieces, seconds) of the finished beginning: every piece in it spoken and timed."""
        secs = 0.0
        for k, p in enumerate(pieces):
            if p["say"] and p["i"] not in times:
                return k, secs
            secs += (times[p["i"]][3] if p["say"] else 0.0) + p["pause"]
        return len(pieces), secs

    def maybe_release():
        nonlocal release
        upto, secs = ready_prefix()
        if upto >= len(pieces) or secs < release_threshold(release + 1, first):
            return
        nxt = release + 1
        while secs >= release_threshold(nxt + 1, first):
            nxt += 1  # resumed far ahead: skip to the part that fits
        t0s, t1s, seconds = build(upto, job / f"partial-{nxt}.m4a")
        to_token = pieces[upto - 1]["to"]
        res = Result(lang, seconds, _units(t0s, t1s), [], [], {"audioSeconds": round(seconds, 1), "partial": True}, [],
                     engine=engine)
        body = res.to_json()
        body["partial"] = {"release": nxt, "toToken": to_token}
        (job / f"partial-{nxt}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        release = nxt
        write_json(rel_file, {"release": nxt, "audioSeconds": round(seconds, 1), "toToken": to_token})
        for old in job.glob("partial-*.*"):  # keep this part and the one before (it may be downloading)
            try:
                if int(old.stem.split("-")[1].split(".")[0]) < nxt - 1:
                    old.unlink()
            except (ValueError, OSError):
                pass
        on_release({"release": nxt, "audioSeconds": round(seconds, 1), "toToken": to_token})

    # pieces already on disk (resuming): time them first
    for p in spoken:
        if wav_of(p["i"]).exists():
            if stop():  # thousands of pieces can take minutes: a stop asked for here is not kept waiting
                raise InterruptedError("stopped")
            align(p["i"])
    announced = read_json(rel_file)
    if isinstance(announced, dict) and "release" in announced:
        on_release(announced)
    maybe_release()

    for _round in range(2):
        done = sum(weight[p["i"]] for p in spoken if wav_of(p["i"]).exists())
        progress("narrate", done / total)

        def on_piece(i):
            nonlocal done
            done += weight.get(i, 0)
            progress("narrate", done / total)
            align(i)
            maybe_release()

        _run_worker(job, plan["voice"], on_piece, stop, note)
        if stop():
            raise InterruptedError("stopped")
        missing = [p["i"] for p in spoken if not wav_of(p["i"]).exists()]
        if missing:
            raise RuntimeError(f"{len(missing)} pieces were not narrated")
        # a piece whose words mostly did not align was probably misread: speak it again, once
        redo = sorted(bad - retried)
        if not redo:
            break
        progress("align", 1.0)
        note(f"{len(redo)} piece(s) did not match the text well; reading them again")
        retried.update(redo)
        (job / "retried.json").write_text(json.dumps(sorted(retried)))
        for i in redo:
            wav_of(i).unlink(missing_ok=True)
            times.pop(i, None)
        bad.clear()

    progress("encode", 0.0)
    t0s, t1s, seconds = build(len(pieces), job / "audio.m4a")
    units = _units(t0s, t1s)
    aligned = sum(sum(x is not None for x in t[2]) for t in times.values())
    words_total = sum(len(t[0]) for t in times.values())
    stats = {
        "audioSeconds": round(seconds, 1), "pieces": len(pieces), "respoken": len(retried),
        "ctcTimedPct": round(100 * aligned / max(1, words_total), 1), "spokenTokens": len(units),
    }
    for old in job.glob("partial-*.*"):
        old.unlink(missing_ok=True)
    progress("encode", 1.0)
    return Result(lang, seconds, units, [], [], stats, [], engine=engine)
