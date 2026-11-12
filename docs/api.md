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
chose to keep without continuing it. Nothing works on it until the server is started again and
the question about it is answered. Apps that do not know the state can show it as waiting.

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
