# Server API

Every request except `/v1/hello` needs `Authorization: Bearer <token>`. JSON in and out unless noted.
A job's id is a hash of its inputs: sending the same thing twice returns the existing job.

## Transport

Started with `python -m raccontami_sync.serve`, the server speaks HTTPS on port 8765 with a certificate it
made itself (`tls-cert.pem` in the data folder). A client cannot check it against a public authority; it pins
the SHA-256 of the certificate (DER) after showing the reader a code to compare with the server's window: the
first 64 bits of that SHA-256 written as a decimal number of 20 digits, in groups of four
(`0458 4939 0331 2265 6608`; `tls.digit_code`). `RACCONTAMI_TLS=0` gives plain HTTP on the same port.

There is no version handshake: the app does not send its version, and does not act on the server's. The app
ignores fields it does not know. An app from before the encrypted link cannot reach a server that uses it (see
the README, "Your network").

Errors are JSON `{"detail": "<text>"}`. For JSON requests the app shows `401` as "The server refused the token"
and any other error status as "Server error <status>: <detail>". File downloads (`/audio`, `/v1/models/…`) show
the app's own text with the status instead, and a `404` from `GET /v1/positions/…` is not an error to it.
Stories in a language other than English and Italian are never sent: the app syncs them on the phone.

## Health

`GET /v1/hello` (no token) → `{"app": "raccontami", "name", "version"}`. Used by the app's "Search local network" to recognize the server.

`GET /v1/health` → `{"ok", "version", "name", "gpu", "queue", "languages": ["en","it"], "narration": {"it": "<voice label>", ...}, "voices": {"it": [{"id", "label", "gender"}], ...}, "freeBytes", "gpuShare", "latestUrl"}`. `languages`: those the server syncs: the installed ones (`RACCONTAMI_LANGUAGES`, English and Italian when it is not set) plus any added with `RACCONTAMI_ALIGN_MODEL_<XX>`. `narration`: the voice of each language the server narrates, only for languages whose voice model is installed. A job or narration in a language missing from these lists gets `400` with a `detail` in plain words for the phone to show (no technical terms, and none of the words app 0.1.5 takes for an unreachable server). `voices`: the further voices a narrator can be given, per language (absent: one voice only). `freeBytes`, `gpuShare` and `latestUrl` are for the server's own page. The app's "Test and save" calls this and shows `name`, `gpu` and `queue`.

The language endpoints are for the server's own page; the app does not need them.

`GET /v1/languages` → `{"languages": [{"code", "name", "installed", "tested", "makesNarrator", "voice", "narrator", "add", "bytes"}, ...], "shared", "adding": {"code", "step", "error"}, "narrator"}`. Every language the server knows, installed or not. `add`: `"here"` when the page can add it, `"installer"` when it needs a voice model only the installer adds. `bytes`: the space its files take. `shared`: the models are in a Hugging Face folder other programs share, so removing a language keeps its downloaded models (a narrator made here and a voice model's environment are still deleted). `adding`: the language being added (`step` is `model`, `narrator` or `done`; `error` in plain words). `narrator`: the default narrator description.

`POST /v1/languages/{code}/remove` with `{"dryRun": true}` → `{"bytes", "shared", "unusedVoices": {"<voice>": {"label", "bytes"}}}`: what removing would free, and the voice models no remaining language would need. Without `dryRun`, with optional `"voices": ["<voice>", ...]` (from `unusedVoices`) → `{"removed", "freedBytes", "shared"}`: the language leaves `RACCONTAMI_LANGUAGES`, and its word-timing model, its narrator made here and the named voice models are deleted. `400` for the last language or one that is not installed; `409` while a language is being added, while the language has unfinished work, or while any work runs when voice models are to be deleted.

`POST /v1/languages/{code}/add` with optional `{"narrator": "<description>"}` → `{"adding": code}`, then works in the background (follow it with `GET /v1/languages`): downloads the word-timing model, makes the narrator for a language that needs one, and adds the language to `RACCONTAMI_LANGUAGES`. `404` for an unknown language, `400` if it is installed, `409` if it needs a voice model that is not installed (the detail says to use the installer), while another language is being added, or while work runs when a narrator must be made.

`POST /v1/gpu-share` with `{"share": 50}` → `{"share"}`: how much of the graphics card the work may take, in % from 10 to 100, running work included, until the server stops (then `RACCONTAMI_GPU_SHARE` again). `GET /v1/health` says the current one as `gpuShare`.

## Jobs (sync and narration)

`GET /v1/jobs/{id}` →
```json
{"id": "...", "kind": "sync|narrate", "state": "queued|running|done|failed",
 "stage": "decode|transcribe|match|align|narrate|encode|done", "progress": 0.42,
 "etaSeconds": 3600, "error": null,
 "partial": {"release": 2, "audioSeconds": 1200.0, "toToken": 5321}}
```
`partial` (narrations only): the latest part of the book that can already be downloaded.

`error` (failed jobs) is a sentence for the person with the phone: the cause in plain words when the server
knows it (graphics memory, a full disk, unreadable audio, the driver, a model download), otherwise a pointer
to the server's page. The raw error is only in `GET /v1/jobs` and the log. App 0.1.5 takes an error that
contains "connection", "network", "refused", "timeout" and a few more words for an unreachable server and
keeps waiting, so these texts avoid them (`unfinished.for_phone`, tested in `tests/test_unfinished.py`).

A job the server does not know is `404` with a `detail` that says so and asks to send the story again.

`state` can also be `held` (with `stage` `held`): an unfinished job that the person at the server
chose to keep without continuing it. Nothing works on it until it is continued from the server's
page, or the server is started again and the question about it is answered. Apps that do not know
the state can show it as waiting.

### For the server's own page

`GET /` → the page (no token: it holds no secret, and asks for the token itself).

`GET /v1/jobs` → every job, as above but with the raw `error`, plus `about` (what it is, in words), `holding` (a hold was
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

`DELETE /v1/jobs/{id}` → stops a narration and deletes its files; also deletes a sync that is waiting, on hold
or failed (the phone syncs it itself, or no longer has the story). A running sync is `409`: it ends by itself.

### Sync an audiobook

`POST /v1/jobs`, multipart: `audio` = the file, `meta` = `{"lang": "en|it", "tokens": [...]}`.
Tokens are the book's words split at whitespace, in order; the sync file refers to their indexes.

### Narrate a text

`POST /v1/narrations` with `{"lang": "en|it", "tokens": [...], "paragraphs": [first token index of each paragraph]}`
and optionally:

- `start`: the first token to read; the words before it (title page, index) are in the text but not narrated.
  Left out for 0, so a book sent before it existed keeps its job.
- `silent`: token indexes that are in the text but never spoken (the symbols that mark a narrator).
- `narrators`: `[[firstToken, "<narrator>"], ...]`, in increasing order, and `cast`: `{"<narrator>": "<voice id>"}`
  with ids from `voices` in `/v1/health`. Both or neither: without them, one voice reads everything.

A language without a voice, or a body that does not fit, is `400`.

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

## Reading positions

So that a second phone or tablet continues where the first stopped. The book is named by a key the
app computes from its text (a hex hash, 16 to 64 characters), so the server does not need the book.
The position is a word of the text (its token number), not a time in the audio.

- `PUT /v1/positions/<key>` with `{"token": 1234, "at": <epoch ms>, "device": "<id>", "name": "<shown name>"}`:
  kept if newer than what the server has. Answers with the newest position known, which may be another device's.
- `GET /v1/positions/<key>`: the newest position, or 404 when the server has none for this book.

## Phone models

`GET /v1/models` → file names; `GET /v1/models/{name}` → the file
(`<model>.int8.onnx`, `<model>.vocab.json`, made by `tools/export_phone_model.py`). The app downloads
these from the `models-v1` GitHub release first and asks the server only when that fails; it checks the
file's SHA-256 against the published one either way.
