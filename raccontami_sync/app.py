"""Raccontami sync server.

  POST /v1/jobs              multipart: audio=<file>, meta=<json {"lang","tokens"}>  -> {"id", "state"}
  GET  /v1/jobs/{id}         -> {"state","stage","progress","etaSeconds","error"}
  GET  /v1/jobs/{id}/result  -> sync JSON (see pipeline.Result.to_json)
  GET  /v1/hello             -> {"app": "raccontami", "name", "version"}  (no token)
  GET  /v1/health            -> {"ok", "gpu", "queue"}

  POST /v1/narrations        JSON {"lang", "tokens", "paragraphs": [first token of each paragraph]}
                             -> {"id", "state"}: the desktop narrates the text with the language's voice
  GET  /v1/jobs/{id}/audio   -> the narrated audio (AAC in .m4a), once the narration is done
       /v1/jobs/{id}/audio?part=N and /v1/jobs/{id}/result?part=N -> part N while narrating:
                             the finished beginning of the book (the job view's "partial" says
                             the latest N, its audio length and its last token)
  DELETE /v1/jobs/{id}       -> stops a narration and deletes its pieces (the story was deleted on the phone),
                                or deletes a sync the server is not working on (409 while it runs)

Narrations run on their own queue, so a book narrated overnight does not hold up
audiobook syncs (unless RACCONTAMI_ONE_JOB=1: then they take turns, for small GPUs).
They resume after a restart from the last finished piece.

Every request needs "Authorization: Bearer <token>". The token is read from
RACCONTAMI_TOKEN or from <data>/token.txt, created on first start.

A job's id is a hash of its audio and tokens, so sending the same project
twice returns the existing job (or its finished result) instead of redoing it.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import secrets
import shutil
import threading
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from .paths import DATA, MODELS as MODELS_DIR, ONNX  # noqa: E402
os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf"))
os.environ.setdefault("TORCH_HOME", str(MODELS_DIR / "torch"))

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile  # noqa: E402

from . import awake, connect_window, narrate, pipeline, single, tray, unfinished  # noqa: E402
from .gate import Gate  # noqa: E402
from .jsonfile import read_json, write_json  # noqa: E402
from .positions import Positions, valid as valid_position  # noqa: E402

JOBS = DATA / "jobs"
JOBS.mkdir(parents=True, exist_ok=True)
LOG = DATA / "server.log"
DELETED = "deleted"  # empty file in a job folder: the phone deleted this story


def log(msg: str) -> None:
    """One readable line in the server window and in server.log."""
    now = time.localtime()
    line = time.strftime("%H:%M:%S", now) + "  " + msg
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d ", now) + line + "\n")
    except OSError:
        pass


def hm(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"


LANG_NAMES = {"en": "English", "it": "Italian"}
# how the app names this server in its texts ("Narrate it on <name>"); the user can change it there too
NAME = os.environ.get("RACCONTAMI_NAME") or __import__("platform").node() or "Raccontami server"
STAGE_NAMES = {"decode": "reading the audio", "transcribe": "listening (Whisper)", "match": "matching the text",
               "align": "timing the words", "narrate": "preparing the voice", "encode": "writing the audio file"}


def _token() -> str:
    env = os.environ.get("RACCONTAMI_TOKEN")
    if env:
        return env
    f = DATA / "token.txt"
    if not f.exists():
        f.write_text(secrets.token_urlsafe(24), encoding="utf-8")
    return f.read_text(encoding="utf-8").strip()


TOKEN = _token()


def auth(authorization: str = Header(default="")):
    if not secrets.compare_digest(authorization, f"Bearer {TOKEN}"):
        raise HTTPException(status_code=401, detail="bad token")


class JobState:
    """Progress of one job, persisted to status.json so a restart keeps finished work."""

    def __init__(self, job_id: str, kind: str = "sync"):
        self.id = job_id
        self.kind = kind
        self.cancelled = False
        self.hold = False  # asked to stop and keep everything (the server's page): see hold_job
        self.about = None  # what the job is, in words, for the server's page (worked out once)
        self.facts: dict = {}  # the same, as separate facts (see unfinished.facts)
        self.pieces_total = None  # narrations: how many pieces of audio, once planned
        self.pieces_done, self.counted_at = 0, -1e9  # and how many are made, counted now and then
        self.partial = None  # narrations: latest published part {"release", "audioSeconds", "toToken"}
        self.dir = JOBS / job_id
        self.state = "queued"
        self.stage = "queued"
        self.progress = 0.0
        self.error = None
        self.started = None
        self.base = 0.0  # progress when this run started: more than 0 for a narration resumed after a restart
        self.saved_at = 0.0
        self.history: list[tuple[float, float]] = []  # (time, progress) for the ETA

    def begin(self):
        """The worker picked the job up."""
        self.state, self.started, self.base = "running", time.monotonic(), self.progress
        self.save()

    def set_progress(self, stage: str, frac: float):
        done = 0.0
        for name, weight in (narrate.STAGES if self.kind == "narrate" else pipeline.STAGES):
            if name == stage:
                done += weight * frac
                break
            done += weight
        if stage != self.stage and self.state == "running":
            log(f"{self.label()}: {STAGE_NAMES.get(stage, stage)}")
        self.stage, self.progress = stage, max(self.progress, min(done, 0.999))
        step = int(self.progress * 10)
        if step > getattr(self, "_logged_step", 0) and self.state == "running":
            self._logged_step = step
            eta = self.eta()
            log(f"{self.label()}: {step * 10} %" + (f", about {hm(eta)} left" if eta else ""))
        now = time.monotonic()
        self.history.append((now, self.progress))
        self.history = [h for h in self.history if now - h[0] < 120]  # last two minutes
        # keep the progress on disk too, so after a restart the phone does not see it fall back to 0
        if self.state == "running" and now - self.saved_at >= 30:
            self.saved_at = now
            try:
                self.save()
            except OSError:
                pass  # the next save will do; reporting progress must never stop the job

    def label(self) -> str:
        return ("narration " if self.kind == "narrate" else "sync ") + self.id[:8]

    def eta(self):
        if self.state != "running" or self.progress < 0.03 or len(self.history) < 2:
            return None
        (t0, p0), (t1, p1) = self.history[0], self.history[-1]
        if p1 <= p0 or t1 - t0 < 5:
            # only what this run did: a resumed narration starts far from 0
            elapsed = time.monotonic() - self.started
            rate = (self.progress - self.base) / elapsed if elapsed > 0 else 0
        else:
            rate = (p1 - p0) / (t1 - t0)
        return round((1 - self.progress) / rate) if rate > 0 else None

    def save(self):
        write_json(self.dir / "status.json",
                   {"state": self.state, "stage": self.stage, "progress": self.progress, "error": self.error,
                    "kind": self.kind})

    def view(self):
        return {"id": self.id, "kind": self.kind, "state": self.state, "stage": self.stage,
                "progress": round(self.progress if self.state != "done" else 1.0, 4),
                "etaSeconds": self.eta(), "error": self.error, "partial": self.partial}


# one job at a time on the GPU: a narration voice and Whisper together need ~12 GB
ONE_JOB = os.environ.get("RACCONTAMI_ONE_JOB") == "1"
pipeline.check_whisper_model(pipeline.WHISPER_MODEL)
models = pipeline.Models(MODELS_DIR, one_job=ONE_JOB)
jobs: dict[str, JobState] = {}
work: "queue.Queue[str]" = queue.Queue()
narrations: "queue.Queue[str]" = queue.Queue()
stopping = threading.Event()  # the server is ending on purpose (its icon, Ctrl+C): see _narration_worker
HIDDEN = os.environ.get("RACCONTAMI_WINDOWLESS") == "1"  # started without a window (background.py)
_lock = None  # kept open while the server runs: one server per data folder (single.py)


def _recovered_status(d: Path):
    """A status for a job whose status.json cannot be read: finished when its result is there,
    to be run again when what the phone sent is there, otherwise None."""
    kind = "narrate" if d.name.startswith("n") else "sync"  # narration ids start with "n" (create_narration)
    if (d / "result.json").exists():
        return {"state": "done", "stage": "done", "progress": 1.0, "error": None, "kind": kind}
    if (d / "meta.json").exists():
        return {"state": "queued", "stage": "queued", "progress": 0.0, "error": None, "kind": kind}
    return None


def _load_existing():
    loaded = []
    for d in JOBS.iterdir():
        if (d / DELETED).exists():  # deleted on the phone while it was running, and the server stopped first
            shutil.rmtree(d, ignore_errors=True)
            log(f"  job {d.name[:8]}: deleted on the phone before the last stop; removed")
            continue
        st = d / "status.json"
        if not st.exists():
            continue
        s = read_json(st)
        if not isinstance(s, dict) or "state" not in s:
            s = _recovered_status(d)
            if s is None:
                log(f"  job {d.name[:8]} skipped: its status file cannot be read and it has nothing to resume from")
                continue
            log(f"  job {d.name[:8]}: its status file was damaged (a power cut?); taken as {s['state']}")
        s.setdefault("kind", "sync")
        loaded.append((d, s))

    # unfinished work: with somebody at the keyboard, asked about one by one (see unfinished.py)
    found = [(d, s) for d, s in loaded if unfinished.is_unfinished(d, s)]
    asked = {}
    # a hidden console still looks like a keyboard: a question there would wait where nobody can see it
    if found and not HIDDEN and unfinished.interactive():
        asked = unfinished.choose(found, seconds=unfinished.wait_seconds())
    elif HIDDEN and tray.why_not() is None:
        # started without a window: there is nowhere to ask, and taking the GPU unasked at login is
        # the opposite of asking. What was waiting or running is kept on hold, and the icon says so.
        asked = {d.name: unfinished.HOLD for d, s in found if s["state"] in ("queued", "running")}
    for d, s in loaded:
        choice = unfinished.LEAVE
        if unfinished.is_unfinished(d, s):
            choice = asked.get(d.name) or unfinished.default_choice(s)
        if choice == unfinished.DELETE:
            shutil.rmtree(d, ignore_errors=True)
            log(f"  job {d.name[:8]}: unfinished; deleted as answered at the start")
            continue
        j = JobState(d.name, s["kind"])
        if s["state"] != "done":
            j.partial = read_json(d / "release.json")  # None when there is no part yet, or the file is damaged
        j.state, j.stage = s["state"], s.get("stage", s["state"])
        j.progress, j.error = float(s.get("progress") or 0.0), s.get("error")
        if choice == unfinished.CONTINUE:  # run again (narrations keep their pieces)
            j.state, j.stage, j.error = "queued", "queued", None
            if j.kind == "sync":
                j.progress = 0.0
            j.save()
            (narrations if j.kind == "narrate" else work).put(j.id)
        elif choice == unfinished.HOLD:
            j.state, j.stage, j.error = unfinished.HELD, unfinished.HELD, None
            j.save()
        jobs[j.id] = j


def _worker():
    while True:
        try:
            job_id = work.get(timeout=30)
        except queue.Empty:
            if models.unload_if_idle():
                log("idle for 10 min: models unloaded from the GPU")
            continue
        j = jobs.get(job_id)
        if j is None or j.state != "queued":  # put on hold, or deleted, while it waited
            continue
        if ONE_JOB and models.turn.locked():
            log(f"{j.label()}: waits for the narration to finish (RACCONTAMI_ONE_JOB)")
        # taken before begin(), so a job that waits still shows as queued; the computer stays awake while it runs
        with models.turn, awake.while_working():
            if j.state != "queued":
                continue
            j.begin()
            log(f"{j.label()}: started")
            try:
                meta = json.loads((j.dir / "meta.json").read_text(encoding="utf-8"))
                audio = next(j.dir.glob("audio.*"))
                res = pipeline.run(models, audio, meta["tokens"], meta["lang"],
                                   progress=lambda s, f: j.set_progress(s, f),
                                   transcript_cache=j.dir / "transcript.json")
                (j.dir / "result.json").write_text(json.dumps(res.to_json(), ensure_ascii=False), encoding="utf-8")
                j.state, j.stage, j.progress = "done", "done", 1.0
                log(f"{j.label()}: done in {hm(time.monotonic() - j.started)} "
                    f"({res.stats.get('matchedPct')} % of the words found in the audio)")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                j.state, j.error = "failed", f"{type(e).__name__}: {e}"
                log(f"{j.label()}: FAILED: {j.error}")
            j.save()


def _narration_worker():
    while True:
        j = jobs.get(narrations.get())
        if stopping.is_set():  # the server is being stopped: what waits stays as it is, for the next start
            return
        if j is None or j.cancelled or j.state != "queued":  # deleted, or put on hold, while it waited
            continue
        if ONE_JOB and models.turn.locked():
            log(f"{j.label()}: waits for the sync to finish (RACCONTAMI_ONE_JOB)")
        # taken before begin(), so a narration that waits still shows as queued; the computer stays awake while it runs
        with models.turn, awake.while_working():
            if j.cancelled or j.state != "queued":  # the same, while it waited for its turn
                continue
            if ONE_JOB and models.unload_whisper():
                log("Whisper unloaded from the GPU to make room for the voice (RACCONTAMI_ONE_JOB)")
            j.begin()
            log(f"{j.label()}: started (preparing the voice can take a few minutes the first time)")

            def on_release(info, j=j):
                j.partial = info
                log(f"{j.label()}: part {info['release']} ready for the phone, {hm(info['audioSeconds'])} of audio")

            try:
                res = narrate.run(models, j.dir, DATA, progress=lambda s, f: j.set_progress(s, f),
                                  stop=lambda j=j: j.cancelled or j.hold or stopping.is_set(), on_release=on_release,
                                  note=lambda msg, j=j: log(f"{j.label()}: {msg}"))
                if j.cancelled:
                    raise InterruptedError("cancelled")
                (j.dir / "result.json").write_text(json.dumps(res.to_json(), ensure_ascii=False), encoding="utf-8")
                j.state, j.stage, j.progress, j.partial = "done", "done", 1.0, None
                log(f"{j.label()}: done, {hm(res.duration)} of audio in {hm(time.monotonic() - j.started)}"
                    + (f" ({res.stats['respoken']} pieces read again)" if res.stats.get("respoken") else ""))
            except Exception as e:  # noqa: BLE001
                if j.cancelled:
                    shutil.rmtree(j.dir, ignore_errors=True)
                    log(f"{j.label()}: stopped and deleted (the story was deleted on the phone)")
                    continue
                if stopping.is_set():
                    # the server is being stopped on purpose: the status on disk still says "running",
                    # which is what makes the next start ask about it. Nothing is marked as failed.
                    log(f"{j.label()}: stopped with the server, its finished pieces are kept")
                    return
                if j.hold:  # stopped on purpose: every finished piece stays, nothing is marked as failed
                    j.hold = False
                    j.state, j.stage, j.error = unfinished.HELD, unfinished.HELD, None
                    j.save()
                    # the reason to put work on hold is often to leave the GPU to something else
                    busy = any(x.state == "running" for x in jobs.values())
                    freed = not busy and models.unload_now()
                    log(f"{j.label()}: put on hold, its finished pieces are kept"
                        + ("; models unloaded from the GPU" if freed else ""))
                    continue
                traceback.print_exc()
                j.state, j.error = "failed", f"{type(e).__name__}: {e}"
                log(f"{j.label()}: FAILED: {j.error}")
            j.save()


def _gpu_name() -> str | None:
    """The GPU's name, or None without one. CUDA can be installed with no card to use
    (hidden from this process, or a driver without a device): that is "no GPU", not an error."""
    import torch

    try:
        return torch.cuda.get_device_name(0) if torch.cuda.is_available() and torch.cuda.device_count() > 0 else None
    except (AssertionError, RuntimeError):
        return None


@asynccontextmanager
async def _lifespan(_app):
    global _lock
    _lock = single.take(DATA)  # before anything looks at the jobs: see single.py
    if _lock is None:
        log(f"NOT STARTED: a Raccontami server is already running on {DATA}. Use that one (its icon next to the "
            "clock, or its page); stop it first to start another")
        raise RuntimeError("a Raccontami server is already running on this data folder")
    _load_existing()
    threading.Thread(target=_worker, daemon=True).start()
    threading.Thread(target=_narration_worker, daemon=True).start()
    import torch

    gpu = _gpu_name() or "no CUDA GPU found"
    log("Raccontami server started")
    log(f"  GPU: {gpu}")
    log(f"  voices: " + ", ".join(f"{LANG_NAMES.get(k, k)}: {v.get('label', v['engine'])}"
                                  for k, v in narrate.voices(DATA).items()))
    log(f"  sync: Whisper {pipeline.WHISPER_MODEL}" + ("; one job at a time on the GPU" if ONE_JOB else ""))
    log(f"  name: {NAME}   (shown in the app; set RACCONTAMI_NAME to change it)")
    # the token goes to the window only, never into a log: logs get shared when asking for help
    if HIDDEN:  # no window: what is printed ends in a file
        log(f"  token for the app: in {DATA / 'token.txt'} (the icon's menu shows it: Connect the phone)")
    else:
        print(f"          token for the app: {TOKEN}", flush=True)
        log(f"  token for the app: shown above, and in {DATA / 'token.txt'}")
    code = os.environ.get("RACCONTAMI_TLS_CODE")  # set by serve.py when the link is encrypted
    if code:
        log(f"  encrypted link: yes. The app shows this code when it connects; check that it is the same: {code}")
    else:
        log("  encrypted link: no (plain HTTP). Others on the same network can read what passes; see the README")
    address = tray.lan_address()
    for_phone = tray.own_url().replace("localhost", address).rstrip("/") if address else None
    if for_phone:
        log(f"  address for the app: {for_phone}   (or \"Search local network\" in the app)")
    log(f"  data: {DATA}")
    waiting = [j for j in jobs.values() if j.state == "queued"]
    if waiting:
        log(f"  resuming {len(waiting)} unfinished job(s): " + ", ".join(j.label() for j in waiting))
    held = [j for j in jobs.values() if j.state == unfinished.HELD]
    if held:
        log(f"  on hold, not worked on: " + ", ".join(j.label() for j in held)
            + ". Continue them from the server's page, or start the server in a window to be asked again")
    log(f"  page: this server's address in a browser (on this computer: {tray.own_url()}) "
        "shows the work, and can put it on hold or continue it")
    # the token is read by somebody at this computer, as in the window; with RACCONTAMI_TOKEN there is no file
    icon = tray.start(NAME, work_summary, work_can, hold_everything, continue_everything, stop_server, log, folder=DATA,
                      connect=lambda: connect_window.facts(for_phone, TOKEN, DATA / "token.txt", code))
    if icon is not None and HIDDEN:  # no window: without a word, a double click would seem to do nothing
        icon.announce("The server is running. This icon opens its page, shows how to connect the phone, and stops it."
                      + (f" {len(held)} unfinished job(s) are kept on hold: continue them from this icon's menu."
                         if held else ""))
    yield
    stopping.set()  # also on Ctrl+C: a narration that is still being stopped is not written down as failed
    if icon is not None:
        icon.stop()


app = FastAPI(title="Raccontami sync server", version="0.1.0", lifespan=_lifespan)
# token and size are checked here, before any of a request's body is read (see gate.py)
MAX_UPLOAD = 4 * 1024 ** 3  # an audiobook; long ones are around 1 GB
MAX_BODY = 64 * 1024 ** 2  # everything else, the text of a long book included
app.add_middleware(Gate, token=TOKEN, open_paths=("/v1/hello", "/"), default_limit=MAX_BODY, limits={"/v1/jobs": MAX_UPLOAD})


@app.get("/v1/hello")
def hello():
    """No token needed: lets the app's "Search local network" recognize this server.
    Says only that it is a Raccontami server, its name and version."""
    return {"app": "raccontami", "name": NAME, "version": app.version}


@app.get("/v1/health", dependencies=[Depends(auth)])
def health():
    import torch

    return {"ok": True, "version": app.version, "name": NAME,
            "gpu": _gpu_name(),
            "queue": work.qsize(), "languages": sorted(pipeline.ALIGN_MODELS),
            "narration": {lang: v.get("label", v["engine"]) for lang, v in narrate.voices(DATA).items()},
            # the voices a narrator can be given, per language (none: one voice only)
            "voices": {lang: [{"id": k, "label": v["label"], "gender": v["gender"]}
                              for k, v in narrate.voice_library(DATA, lang).items()]
                       for lang in narrate.voices(DATA) if narrate.voice_library(DATA, lang)}}


def _outdated(j: JobState) -> bool:
    """A finished job whose result predates the current sync format is redone
    (the transcript is cached, so this only reruns matching and alignment)."""
    if j.state != "done":
        return False
    try:
        return json.loads((j.dir / "result.json").read_text(encoding="utf-8")).get("version", 1) < 3
    except Exception:
        return True


@app.post("/v1/jobs", dependencies=[Depends(auth)])
def create_job(audio: UploadFile = File(...), meta: str = Form(...)):
    try:
        m = json.loads(meta)
        lang, tokens = m["lang"], m["tokens"]
        assert lang in pipeline.ALIGN_MODELS and isinstance(tokens, list) and tokens
        assert all(isinstance(t, str) for t in tokens)
    except Exception:
        raise HTTPException(status_code=400, detail="meta must be JSON with lang (en|it) and a non-empty tokens list")

    tmp = JOBS / f"upload-{secrets.token_hex(6)}"
    h = hashlib.sha256()
    with open(tmp, "wb") as f:
        while chunk := audio.file.read(1 << 20):
            h.update(chunk)
            f.write(chunk)
    h.update(json.dumps({"lang": lang, "tokens": tokens}, ensure_ascii=False).encode())
    job_id = h.hexdigest()[:20]

    if job_id in jobs and jobs[job_id].state != "failed" and not _outdated(jobs[job_id]):
        tmp.unlink()
        return jobs[job_id].view()

    j = JobState(job_id)
    transcript = None
    if (j.dir / "transcript.json").exists():
        transcript = (j.dir / "transcript.json").read_text(encoding="utf-8")
    if j.dir.exists():
        shutil.rmtree(j.dir)
    j.dir.mkdir(parents=True)
    if transcript is not None:
        (j.dir / "transcript.json").write_text(transcript, encoding="utf-8")
    suffix = Path(audio.filename or "audio.mp3").suffix.lower() or ".mp3"
    tmp.replace(j.dir / f"audio{suffix}")
    (j.dir / "meta.json").write_text(json.dumps({"lang": lang, "tokens": tokens}, ensure_ascii=False), encoding="utf-8")
    unfinished.write_label(j.dir, m.get("title"), m.get("device"))  # for people: not part of what the job is
    j.save()
    jobs[job_id] = j
    work.put(job_id)
    log(f"{j.label()}: received from the phone, {LANG_NAMES.get(lang, lang)}, {len(tokens):,} words, "
        f"{(j.dir / f'audio{suffix}').stat().st_size / 1e6:.0f} MB of audio; queued")
    return j.view()


@app.post("/v1/narrations", dependencies=[Depends(auth)])
def create_narration(body: dict = Body(...)):
    try:
        lang, tokens, paragraphs = body["lang"], body["tokens"], body["paragraphs"]
        assert lang in narrate.voices(DATA) and lang in pipeline.ALIGN_MODELS
        assert isinstance(tokens, list) and tokens and all(isinstance(t, str) for t in tokens)
        assert isinstance(paragraphs, list) and all(isinstance(p, int) for p in paragraphs)
        # the first word to read: what is before it (title page, index) is in the text but not narrated
        start = body.get("start", 0)
        assert isinstance(start, int) and not isinstance(start, bool) and 0 <= start < len(tokens)
        # words that are in the text but never spoken: the symbols that mark who narrates
        silent = body.get("silent", [])
        assert isinstance(silent, list) and all(isinstance(k, int) and not isinstance(k, bool) and 0 <= k < len(tokens) for k in silent)
        silent = sorted(set(silent))
        # who narrates from which word on, and the voice of each: see narrate.plan_pieces
        narrators = body.get("narrators", [])
        assert isinstance(narrators, list) and len(narrators) <= 50_000
        assert all(isinstance(p, list) and len(p) == 2 and isinstance(p[0], int) and not isinstance(p[0], bool)
                   and 0 <= p[0] < len(tokens) and isinstance(p[1], str) and len(p[1]) <= 60 for p in narrators)
        assert all(a[0] < b[0] for a, b in zip(narrators, narrators[1:]))
        cast = body.get("cast", {})
        assert isinstance(cast, dict) and len(cast) <= 200
        assert all(isinstance(k, str) and isinstance(v, str) and 0 < len(v) <= 60 for k, v in cast.items())
        cast = dict(sorted(cast.items()))
        if not cast or not narrators:  # one voice for everything
            narrators, cast = [], {}
    except Exception:
        raise HTTPException(status_code=400, detail="body must be JSON with lang, a non-empty tokens list, paragraphs, "
                                                    "and optional start, silent, narrators and cast")
    voice = narrate.voices(DATA)[lang]
    key = {"kind": "narrate", "v": narrate.VERSION, "lang": lang, "tokens": tokens, "paragraphs": paragraphs,
           "voice": {k: v for k, v in voice.items() if k != "python"}}
    if start:
        key["start"] = start  # left out for 0, so books sent before this existed keep their job
    if silent:
        key["silent"] = silent
    if cast:
        key["narrators"], key["cast"] = narrators, cast
    job_id = "n" + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:19]
    j = jobs.get(job_id)
    if j is not None and j.state != "failed":
        # the name can arrive later than the job: an app from before it sent one, updated since
        unfinished.write_label(j.dir, body.get("title"), body.get("device"))
        j.about = None
        return j.view()
    retry = j is not None
    j = JobState(job_id, "narrate")
    j.dir.mkdir(parents=True, exist_ok=True)  # a failed narration keeps its finished pieces
    unfinished.write_label(j.dir, body.get("title"), body.get("device"))  # for people: not part of what the job is
    (j.dir / DELETED).unlink(missing_ok=True)  # sent again after being deleted: it is wanted again
    (j.dir / "meta.json").write_text(json.dumps({"lang": lang, "tokens": tokens, "paragraphs": paragraphs, "start": start, "silent": silent,
                                                 "narrators": narrators, "cast": cast},
                                                ensure_ascii=False), encoding="utf-8")
    j.save()
    jobs[job_id] = j
    narrations.put(job_id)
    log(f"{j.label()}: {'sent again' if retry else 'received'} from the phone, {LANG_NAMES.get(lang, lang)}, "
        f"{len(tokens):,} words (about {hm(len(tokens) / 2.5)} of audio); queued")
    return j.view()


@app.get("/v1/jobs/{job_id}/audio", dependencies=[Depends(auth)])
def job_audio(job_id: str, part: int = 0):
    from fastapi.responses import FileResponse

    j = jobs.get(job_id)
    if j is None or j.kind != "narrate":
        raise HTTPException(status_code=404, detail="unknown narration")
    if part:
        f = j.dir / f"partial-{part}.m4a"
        if not f.exists():
            raise HTTPException(status_code=404, detail="no such part (a newer one may be out)")
        log(f"{j.label()}: the phone is downloading part {part}")
        return FileResponse(f, media_type="audio/mp4", filename=f.name)
    if j.state != "done":
        raise HTTPException(status_code=409, detail=f"narration is {j.state}")
    log(f"{j.label()}: the phone is downloading the finished narration")
    return FileResponse(j.dir / "audio.m4a", media_type="audio/mp4", filename="audio.m4a")


@app.delete("/v1/jobs/{job_id}", dependencies=[Depends(auth)])
def delete_job(job_id: str):
    """Deletes a narration (a running one stops within seconds), or a sync the server is not working
    on: the phone syncs it itself now, or no longer has the story. A running sync ends by itself."""
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    if not unfinished.can_delete({"state": j.state, "kind": j.kind}):
        raise HTTPException(status_code=409, detail="a sync that is running cannot be stopped: it ends by itself, "
                                                    "usually within minutes")
    j.cancelled = True
    jobs.pop(job_id, None)
    if j.state != "running":  # a running one is removed by its worker once the voice stops
        j.state = "deleted"  # a worker that already took it from the line skips it
        shutil.rmtree(j.dir, ignore_errors=True)
        log(f"{j.label()}: deleted")
    else:
        # the worker may not get to it before the server stops: this mark makes the next start
        # finish the deletion instead of narrating a story the phone no longer has
        try:
            (j.dir / DELETED).touch()
        except OSError:
            pass
    return {"deleted": job_id}


SYNC_CANNOT_HOLD = ("a sync that is running cannot be put on hold: it has no place to stop and pick up again. "
                    "It ends by itself, usually within minutes")


def put_on_hold(j: JobState) -> str | None:
    """Stops working on a job and keeps everything it has made; returns why not, or None.
    A narration that is running stops within seconds (it still says "running" until it has); a job
    that waits is taken out of the line. Used by the server's page and by its icon."""
    if j.state == "queued":
        j.state, j.stage = unfinished.HELD, unfinished.HELD
        j.save()
        log(f"{j.label()}: put on hold while it waited")
    elif j.state == "running" and j.kind == "narrate":
        j.hold = True
    elif j.state == "running":
        return SYNC_CANNOT_HOLD
    elif j.state != unfinished.HELD:
        return f"this job is {j.state}: there is nothing to put on hold"
    return None


def put_back(j: JobState) -> str | None:
    """Puts a job on hold, or a narration that stopped with finished pieces, back in line; returns why not, or None."""
    if j.state in ("queued", "running"):
        j.hold = False  # asked to continue before the hold took effect
        return None
    if not unfinished.can_continue(j.dir, {"state": j.state, "kind": j.kind}):
        return f"this job is {j.state}: there is nothing to continue"
    j.state, j.stage, j.error = "queued", "queued", None
    if j.kind == "sync":
        j.progress = 0.0
    j.save()
    (narrations if j.kind == "narrate" else work).put(j.id)
    log(f"{j.label()}: continued; queued")
    return None


def hold_everything() -> str | None:
    """Everything that can be put on hold is: first what waits (or the next in line would start the
    moment the running one stops), then what runs. Returns what could not be, for the reader."""
    for j in [x for x in list(jobs.values()) if x.state == "queued"]:
        put_on_hold(j)
    refused = [put_on_hold(j) for j in list(jobs.values()) if j.state == "running"]
    return "A sync is still running: it cannot be put on hold, and ends by itself." if any(refused) else None


def continue_everything() -> str | None:
    """Continues what is on hold. A narration that stopped with an error is left to be continued one by one."""
    for j in [x for x in list(jobs.values()) if x.state == unfinished.HELD]:
        put_back(j)
    return None


def work_summary() -> tuple[str, str]:
    """What the server is doing, in a word for the colour of the icon and a line for its tip."""
    all_jobs = list(jobs.values())
    running = [j for j in all_jobs if j.state == "running"]
    waiting = sum(j.state == "queued" for j in all_jobs)
    held = sum(j.state == unfinished.HELD for j in all_jobs)
    if running:
        j = running[0]
        text = ("narrating" if j.kind == "narrate" else "syncing") + f", {int(j.progress * 100)} %"
        if j.hold:
            text = "stopping, to be kept on hold"
        more = len(running) - 1 + waiting
        return "working", text + (f"; {more} more in line" if more else "") + (f"; {held} on hold" if held else "")
    if waiting:
        return "working", f"{waiting} job(s) about to start"
    if held:
        return "hold", f"{held} job(s) on hold, nothing is being worked on"
    return "idle", "nothing to do"


def work_can() -> dict:
    all_jobs = list(jobs.values())
    return {"hold": any(j.state == "queued" or (j.state == "running" and j.kind == "narrate" and not j.hold) for j in all_jobs),
            "continue": any(j.state == unfinished.HELD for j in all_jobs)}


def stop_server() -> None:
    """Stops the server from its icon. A narration in progress is stopped first and left as it is on
    disk ("running"), so the next start asks about it; it is never marked as failed."""
    import signal

    log("stopping, asked from the icon: unfinished work is kept and asked about at the next start")
    stopping.set()

    def leave():
        # the same as Ctrl+C in the window: uvicorn closes what is open and ends
        signal.raise_signal(signal.SIGINT)

    threading.Timer(1.5, leave).start()  # time for the voice to be stopped by its watcher


@app.post("/v1/jobs/{job_id}/hold", dependencies=[Depends(auth)])
def hold_job(job_id: str):
    """Stops working on a job and keeps everything it has made (see put_on_hold). It stays on hold
    until it is continued from the page, from the icon, or at the start of the server."""
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    refusal = put_on_hold(j)
    if refusal:
        raise HTTPException(status_code=409, detail=refusal)
    return j.view()


@app.post("/v1/jobs/{job_id}/continue", dependencies=[Depends(auth)])
def continue_job(job_id: str):
    """Puts a job that is on hold, or a narration that stopped with finished pieces, back in line."""
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    refusal = put_back(j)
    if refusal:
        raise HTTPException(status_code=409, detail=refusal)
    return j.view()


@app.post("/v1/hold", dependencies=[Depends(auth)])
def hold_all():
    """Puts everything that can be on hold: what waits first, then what runs (see hold_everything)."""
    return {"message": hold_everything()}


@app.post("/v1/continue", dependencies=[Depends(auth)])
def continue_all():
    """Continues everything that is on hold."""
    return {"message": continue_everything()}


@app.get("/v1/jobs", dependencies=[Depends(auth)])
def list_jobs():
    """Every job the server knows, for its own page: what the phone sees of each, what it is in words,
    and what can be done with it now."""
    out = []
    now = time.monotonic()
    for j in list(jobs.values()):
        if j.about is None:  # read once: it takes the whole text of the book
            j.facts = unfinished.facts(j.dir, j.kind)
            j.about = unfinished.about(j.dir, j.kind, j.facts)
        details = dict(j.facts)
        if j.kind == "narrate":
            if j.pieces_total is None:
                j.pieces_total = unfinished.pieces_total(j.dir)
            if now - j.counted_at > 10:  # thousands of files: not at every look
                j.counted_at, j.pieces_done = now, unfinished.pieces_done(j.dir)
            details.update(piecesDone=j.pieces_done, piecesTotal=j.pieces_total,
                           audioReadySeconds=(j.partial or {}).get("audioSeconds") if j.state != "done" else None)
        try:
            details["lastWorked"] = int((j.dir / "status.json").stat().st_mtime)
        except OSError:
            details["lastWorked"] = None
        status = {"state": j.state, "kind": j.kind}
        out.append({**j.view(), "about": j.about, "details": details, "holding": j.hold,
                    "can": {"hold": j.state == "queued" or (j.state == "running" and j.kind == "narrate" and not j.hold),
                            "continue": unfinished.can_continue(j.dir, status),
                            "delete": unfinished.can_delete(status)}})
    order = {"running": 0, "queued": 1, unfinished.HELD: 2, "failed": 3, "done": 4}
    return sorted(out, key=lambda v: order.get(v["state"], 5))


@app.get("/", include_in_schema=False)
def page():
    """The server's own page. It holds no secret: what it shows and does goes through the routes
    above, with the token the reader types into it once."""
    from fastapi.responses import FileResponse

    return FileResponse(Path(__file__).with_name("page.html"), media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})


@app.get("/v1/jobs/{job_id}", dependencies=[Depends(auth)])
def job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="unknown job")
    return jobs[job_id].view()


# ---- reading positions, so another phone or tablet continues where this one stopped

positions = Positions(DATA / "positions.json")


@app.get("/v1/positions/{key}", dependencies=[Depends(auth)])
def get_position(key: str):
    found = positions.get(key)
    if found is None:
        raise HTTPException(status_code=404, detail="no position for this book")
    return found


@app.put("/v1/positions/{key}", dependencies=[Depends(auth)])
def put_position(key: str, body: dict = Body(...)):
    given = valid_position(key, body)
    if given is None:
        raise HTTPException(status_code=400, detail="body must be JSON with token, at and device; the key is the book's hash")
    return positions.put(key, *given)  # the newest known, which may be another device's


# ---- on-phone sync models (made by server/onnx/export_ctc.py)

MODEL_DIR = ONNX


@app.get("/v1/models", dependencies=[Depends(auth)])
def list_models():
    return sorted(f.name for f in MODEL_DIR.glob("*") if f.name.endswith((".int8.onnx", ".vocab.json")))


@app.get("/v1/models/{name}", dependencies=[Depends(auth)])
def model_file(name: str):
    from fastapi.responses import FileResponse

    f = (MODEL_DIR / name).resolve()
    if f.parent != MODEL_DIR.resolve() or not f.is_file() or not name.endswith((".int8.onnx", ".vocab.json")):
        raise HTTPException(status_code=404, detail="no such model file")
    return FileResponse(f, media_type="application/octet-stream", filename=name)


@app.get("/v1/jobs/{job_id}/result", dependencies=[Depends(auth)])
def job_result(job_id: str, part: int = 0):
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    if part:
        f = j.dir / f"partial-{part}.json"
        if not f.exists():
            raise HTTPException(status_code=404, detail="no such part (a newer one may be out)")
        return json.loads(f.read_text(encoding="utf-8"))
    if j.state != "done":
        raise HTTPException(status_code=409, detail=f"job is {j.state}")
    return json.loads((j.dir / "result.json").read_text(encoding="utf-8"))
