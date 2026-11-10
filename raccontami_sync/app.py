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
  DELETE /v1/jobs/{id}       -> stops a narration and deletes its pieces (the story was deleted on the phone)

Narrations run on their own queue, so a book narrated overnight does not hold up
audiobook syncs. They resume after a restart from the last finished piece.

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

from . import narrate, pipeline  # noqa: E402

JOBS = DATA / "jobs"
JOBS.mkdir(parents=True, exist_ok=True)
LOG = DATA / "server.log"


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
        self.partial = None  # narrations: latest published part {"release", "audioSeconds", "toToken"}
        self.dir = JOBS / job_id
        self.state = "queued"
        self.stage = "queued"
        self.progress = 0.0
        self.error = None
        self.started = None
        self.history: list[tuple[float, float]] = []  # (time, progress) for the ETA

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

    def label(self) -> str:
        return ("narration " if self.kind == "narrate" else "sync ") + self.id[:8]

    def eta(self):
        if self.state != "running" or self.progress < 0.03 or len(self.history) < 2:
            return None
        (t0, p0), (t1, p1) = self.history[0], self.history[-1]
        if p1 <= p0 or t1 - t0 < 5:
            elapsed = time.monotonic() - self.started
            rate = self.progress / elapsed if elapsed > 0 else 0
        else:
            rate = (p1 - p0) / (t1 - t0)
        return round((1 - self.progress) / rate) if rate > 0 else None

    def save(self):
        (self.dir / "status.json").write_text(json.dumps(
            {"state": self.state, "stage": self.stage, "progress": self.progress, "error": self.error,
             "kind": self.kind}), encoding="utf-8")

    def view(self):
        return {"id": self.id, "kind": self.kind, "state": self.state, "stage": self.stage,
                "progress": round(self.progress if self.state != "done" else 1.0, 4),
                "etaSeconds": self.eta(), "error": self.error, "partial": self.partial}


models = pipeline.Models(MODELS_DIR)
jobs: dict[str, JobState] = {}
work: "queue.Queue[str]" = queue.Queue()
narrations: "queue.Queue[str]" = queue.Queue()


def _load_existing():
    for d in JOBS.iterdir():
        st = d / "status.json"
        if not st.exists():
            continue
        s = json.loads(st.read_text(encoding="utf-8"))
        j = JobState(d.name, s.get("kind", "sync"))
        if (d / "release.json").exists() and s["state"] != "done":
            j.partial = json.loads((d / "release.json").read_text(encoding="utf-8"))
        j.state, j.stage, j.progress, j.error = s["state"], s["stage"], s["progress"], s["error"]
        if j.state in ("queued", "running"):  # interrupted by a restart: run again (narrations keep their pieces)
            j.state, j.stage = "queued", "queued"
            if j.kind == "sync":
                j.progress = 0.0
            (narrations if j.kind == "narrate" else work).put(j.id)
        jobs[j.id] = j


def _worker():
    while True:
        try:
            job_id = work.get(timeout=30)
        except queue.Empty:
            if models.unload_if_idle():
                log("idle for 10 min: models unloaded from the GPU")
            continue
        j = jobs[job_id]
        j.state, j.started = "running", time.monotonic()
        j.save()
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
        if j is None or j.cancelled:
            continue
        j.state, j.started = "running", time.monotonic()
        j.save()
        log(f"{j.label()}: started (preparing the voice can take a few minutes the first time)")

        def on_release(info, j=j):
            j.partial = info
            log(f"{j.label()}: part {info['release']} ready for the phone, {hm(info['audioSeconds'])} of audio")

        try:
            res = narrate.run(models, j.dir, DATA, progress=lambda s, f: j.set_progress(s, f),
                              stop=lambda: j.cancelled, on_release=on_release,
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
            traceback.print_exc()
            j.state, j.error = "failed", f"{type(e).__name__}: {e}"
            log(f"{j.label()}: FAILED: {j.error}")
        j.save()


@asynccontextmanager
async def _lifespan(_app):
    _load_existing()
    threading.Thread(target=_worker, daemon=True).start()
    threading.Thread(target=_narration_worker, daemon=True).start()
    import torch

    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no CUDA GPU found"
    log("Raccontami server started")
    log(f"  GPU: {gpu}")
    log(f"  voices: " + ", ".join(f"{LANG_NAMES.get(k, k)}: {v.get('label', v['engine'])}"
                                  for k, v in narrate.voices(DATA).items()))
    log(f"  name: {NAME}   (shown in the app; set RACCONTAMI_NAME to change it)")
    log(f"  token for the app: {TOKEN}   (also in {DATA / 'token.txt'})")
    log(f"  data: {DATA}")
    waiting = [j for j in jobs.values() if j.state == "queued"]
    if waiting:
        log(f"  resuming {len(waiting)} unfinished job(s): " + ", ".join(j.label() for j in waiting))
    yield


app = FastAPI(title="Raccontami sync server", version="0.1.0", lifespan=_lifespan)


@app.get("/v1/hello")
def hello():
    """No token needed: lets the app's "Search local network" recognize this server.
    Says only that it is a Raccontami server, its name and version."""
    return {"app": "raccontami", "name": NAME, "version": app.version}


@app.get("/v1/health", dependencies=[Depends(auth)])
def health():
    import torch

    return {"ok": True, "version": app.version, "name": NAME,
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "queue": work.qsize(), "languages": sorted(pipeline.ALIGN_MODELS),
            "narration": {lang: v.get("label", v["engine"]) for lang, v in narrate.voices(DATA).items()}}


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
    except Exception:
        raise HTTPException(status_code=400, detail="body must be JSON with lang, a non-empty tokens list and paragraphs")
    voice = narrate.voices(DATA)[lang]
    key = {"kind": "narrate", "v": narrate.VERSION, "lang": lang, "tokens": tokens, "paragraphs": paragraphs,
           "voice": {k: v for k, v in voice.items() if k != "python"}}
    job_id = "n" + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:19]
    j = jobs.get(job_id)
    if j is not None and j.state != "failed":
        return j.view()
    retry = j is not None
    j = JobState(job_id, "narrate")
    j.dir.mkdir(parents=True, exist_ok=True)  # a failed narration keeps its finished pieces
    (j.dir / "meta.json").write_text(json.dumps({"lang": lang, "tokens": tokens, "paragraphs": paragraphs},
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
    j = jobs.get(job_id)
    if j is None or j.kind != "narrate":
        raise HTTPException(status_code=404, detail="unknown narration")
    j.cancelled = True
    jobs.pop(job_id, None)
    if j.state != "running":  # a running one is removed by its worker once the voice stops
        shutil.rmtree(j.dir, ignore_errors=True)
    return {"deleted": job_id}


@app.get("/v1/jobs/{job_id}", dependencies=[Depends(auth)])
def job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="unknown job")
    return jobs[job_id].view()


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
