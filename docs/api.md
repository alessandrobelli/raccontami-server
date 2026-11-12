# Server API

Every request except `/v1/hello` needs `Authorization: Bearer <token>`. JSON in and out unless noted.
A job's id is a hash of its inputs: sending the same thing twice returns the existing job.

## Health

`GET /v1/hello` (no token) → `{"app": "raccontami", "name", "version"}`. Used by the app's "Search local network" to recognize the server.

`GET /v1/health` → `{"ok", "version", "name", "gpu", "queue", "languages": ["en","it"], "narration": {"it": "<voice label>", ...}}`

## Jobs (sync and narration)

`GET /v1/jobs/{id}` →
```json
{"id": "...", "kind": "sync|narrate", "state": "queued|running|done|failed",
 "stage": "decode|transcribe|match|align|narrate|encode|done", "progress": 0.42,
 "etaSeconds": 3600, "error": null,
 "partial": {"release": 2, "audioSeconds": 1200.0, "toToken": 5321}}
```
`partial` (narrations only): the latest part of the book that can already be downloaded.

`state` can also be `held` (with `stage` `held`): an unfinished job that the person at the server
chose to keep without continuing it. Nothing works on it until it is continued from the server's
page, or the server is started again and the question about it is answered. Apps that do not know
the state can show it as waiting.

### For the server's own page

`GET /` → the page (no token: it holds no secret, and asks for the token itself).

`GET /v1/jobs` → every job, as above, plus `about` (what it is, in words), `holding` (a hold was
asked for and the voice is stopping), `can`: `{"hold": bool, "continue": bool, "delete": bool}`, and
`details`: `title` and `device` (when the phone sent them), `language`, `words`, `sent` and
`lastWorked` (seconds since 1970) and, for narrations, `beginning`, `audioSecondsAbout`,
`narrators`, `voices`, `piecesDone`, `piecesTotal` and `audioReadySeconds`.

Both `POST /v1/jobs` (in `meta`) and `POST /v1/narrations` take two optional texts, `title` and
`device`: what the story is called and which device sent it. They are shown on the page and in the
question at the start; they are not part of what the job is, so the same book keeps its job.

`POST /v1/jobs/{id}/hold` → stops working on the job and keeps what it made. A waiting job, or a
narration that is running; a running sync answers 409. The answer may still say `running` for a
few seconds.

`POST /v1/jobs/{id}/continue` → puts a job on hold, or a narration that failed with finished
pieces, back in line. 409 when there is nothing to continue.

`GET /v1/jobs/{id}/result[?part=N]` → the sync file (below); with `part`, the part's.

`DELETE /v1/jobs/{id}` → stops a narration and deletes its files.

### Sync an audiobook

`POST /v1/jobs`, multipart: `audio` = the file, `meta` = `{"lang": "en|it", "tokens": [...]}`.
Tokens are the book's words split at whitespace, in order; the sync file refers to their indexes.

### Narrate a text

`POST /v1/narrations` with `{"lang": "en|it", "tokens": [...], "paragraphs": [first token index of each paragraph]}`.

`GET /v1/jobs/{id}/audio[?part=N]` → `audio/mp4` (AAC): the finished narration, or part N while it runs.
Parts grow (the beginning of the book up to `partial.toToken`); their timings match the final file.

## Sync file

```json
{"format": "raccontami-sync", "version": 3, "language": "it", "duration": 812.4,
 "engine": {"anchors": "whisper-<model, turbo by default>", "align": "<model>"}  /* narrations: {"tts": "<voice>", "align": "<model>"} */,
 "units": [[firstToken, lastToken, startSeconds, endSeconds], ...],
 "audioGaps": [{"t0", "t1", "excerpt"}], "textGaps": [{"from", "to"}],
 "corrections": [{"t": token, "w": "spoken word"}],
 "partial": {"release": 2, "toToken": 5321}  /* only in a part */,
 "stats": {...}}
```

## Phone models

`GET /v1/models` → file names; `GET /v1/models/{name}` → the file
(`<model>.int8.onnx`, `<model>.vocab.json`, made by `tools/export_phone_model.py`).
