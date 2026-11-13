# Raccontami server

The GPU companion of **Raccontami**, a reading app that highlights each word of a book
as it is spoken. It runs on a computer with an NVIDIA graphics card, at home or rented,
and does three jobs for the app:

| Job | What it does | Speed on an RTX 5080 |
|---|---|---|
| **Sync** | lines up an audiobook you already have with its text, word by word | a few minutes per book |
| **Narrate** | reads a text aloud with a natural voice, then syncs it | ~1 h of work per 3 h of audio |
| **Phone models** | serves the small models the app uses to sync on the phone itself | – |

Narrations survive restarts: if the computer is turned off, the job continues from the last
finished paragraph when the server starts again. Started in a window, the server asks first about
each unfinished job: continue it now, delete the work done so far, or keep it on hold (nothing
works on it, and the question comes back at the next start). Without an answer within a minute
(`RACCONTAMI_ASK_SECONDS`, 0 = wait for ever) the server goes on by itself: work that was running
continues, and nothing is deleted.
Without a window (a service, Docker) unfinished jobs continue by themselves, as before.
Only one server runs on a data folder: a second start says so and ends, instead of touching the
work of the first.

The server has a page of its own: open its address in a browser (on the same computer,
`https://localhost:8765/` with the encrypted link, which the browser warns about once since the
certificate is the server's own; `http://` with `RACCONTAMI_TLS=0`) and type the token once. It shows what the server is working on, and each
job can be put on hold, continued or deleted there. Putting a narration on hold stops the voice
within seconds and keeps every finished piece: that is the way to leave the graphics card to
something else for a while without stopping the server. A sync that is running cannot be put on
hold; it ends by itself, usually within minutes.

On Windows the server also puts an icon next to the clock (Windows may keep it behind the small
arrow there). Its colour says whether the server is working, on hold or idle; a click opens the
page; its menu puts everything on hold, continues it, or stops the server. Stopping it from there
leaves a narration in progress to be asked about at the next start, instead of marked as failed.
`RACCONTAMI_TRAY=0` switches the icon off; without it the server works the same.

The Windows installer also makes a shortcut that starts the server without a window
(`pythonw -m raccontami_sync.background`): it then lives next to the clock only, so there is no
window to close by mistake in the middle of a narration. Started this way it does not take the
graphics card by itself: unfinished work is kept on hold and the icon says so, until it is
continued from the icon or the page. The token is in `server-data/token.txt` (the icon's menu opens
that folder), and what the window would have shown is in `server-data/window.log`.

While a long book is narrated, the finished
beginning is published in growing parts (a quarter of the book or 10 minutes, then doubling),
so listening can start within minutes.

## Requirements

| | Minimum | Recommended |
|---|---|---|
| GPU | NVIDIA, 8 GB with `RACCONTAMI_ONE_JOB=1` | 12–16 GB |
| Driver | supports CUDA 12.8 (570 or newer; required for RTX 50) | latest |
| Disk | 35 GB | 50 GB on a fast drive (+ ~30 MB per narrated hour) |
| Software | Python 3.12, ffmpeg | |

Graphics memory in use: Whisper turbo ~3 GB (sync), wav2vec2 aligner ~1.5 GB,
VoxCPM2 ~6.5 GB (Italian voice), Qwen3-TTS ~5 GB (English voice). Models leave the GPU
after 10 idle minutes.

A sync and a narration run at the same time, which together take up to ~12 GB. On a smaller
GPU set `RACCONTAMI_ONE_JOB=1` (a commented line is ready in the start script): jobs then take
turns, and Whisper leaves the GPU when a narration starts. The cost is waiting: an audiobook
sent while a book is being narrated starts only when the narration ends, which can be hours.

## Install

Everything goes into one home folder (default `~/raccontami`, or `%USERPROFILE%\raccontami`):
three Python environments (the voices need library versions that conflict with each
other), the models, the jobs. The installers are safe to run again; they only add what is
missing, so running one after `git pull` updates an existing install.

### Windows

```powershell
git clone https://github.com/alessandrobelli/raccontami-server
cd raccontami-server
powershell -ExecutionPolicy Bypass -File install\install-windows.ps1 -RaccontamiHome D:\raccontami
```

Then double-click `D:\raccontami\start-server.bat`. The script prints how to open the
firewall port for your network and how to start the server at login.

### Linux

```bash
git clone https://github.com/alessandrobelli/raccontami-server && cd raccontami-server
RACCONTAMI_HOME=/srv/raccontami ./install/install-linux.sh --service
```

`--service` installs a systemd service that starts at boot and restarts after a crash.

### Rented GPU (Docker)

```bash
docker build -f docker/Dockerfile -t raccontami-server .
docker run --gpus all -p 8765:8765 -v raccontami-data:/data raccontami-server
```

The first start downloads ~20 GB of models into `/data`. **Mount a persistent volume on
`/data`**, so models, unfinished narrations and the token survive the machine being stopped.

**Do not expose port 8765 to the internet over plain HTTP**: the token travels with every
request. Use [Tailscale](https://tailscale.com) (install it on the server and the phone and
use the server's `100.x.y.z` address), or put an HTTPS reverse proxy in front, e.g. Caddy:
`raccontami.example.com { reverse_proxy localhost:8765 }`.

A 4090-class GPU narrates a 10-hour book in about 3.5–4 hours. Stop the machine afterwards:
the app has already downloaded the result.

## Your network

The app and the server talk over an encrypted link. The server makes its own certificate the first
time it starts and keeps it in its data folder. Nobody vouches for a computer at home, so the app
does not ask who signed the certificate: it remembers the one it was paired with.

- **Pairing.** When the app first connects, it shows a short code, like `3fa9-07c2-b1d4-88e0`. The
  server's window shows its code when it starts. Check that they are the same, then confirm in the
  app. If they differ, something between the phone and the computer is pretending to be the server:
  do not confirm.
- **After an update from a version without the encrypted link**, run the installer again (it adds a
  package and a new start file). The server then answers on `https://`, and the app has to be paired
  once: change the address in the app from `http://` to `https://`, or search the network again.
- **An app older than the encrypted link** cannot connect to an encrypted server. Update the app, or
  set `RACCONTAMI_TLS=0` in the start file to stay on plain HTTP for now.
- **Plain HTTP** (`RACCONTAMI_TLS=0`): anyone on the same network can read the token and the text as
  they pass, and then use the server with that token. Use it only on a network you trust, or behind
  something that encrypts for you: [Tailscale](https://tailscale.com) between the computer and the
  phone, or an HTTPS reverse proxy.
- **A new certificate** (the two `tls-*.pem` files in the data folder were deleted, or the data
  folder is new): the app refuses to connect until you pair it again. That is on purpose.

## Connect the app

The server prints its **token** when it starts (also saved in `<home>/server-data/token.txt`).
In the app: **Settings → Server address** (`https://<computer IP>:8765`, the Tailscale address
or your HTTPS address), **Token**, then **Test and save**. The app takes the server's name
for its messages ("Narrate it on Studio PC"); change it under **Name** in the app, or for
every phone with `RACCONTAMI_NAME` on the server.

## Voices

| Language | Voice | Licence |
|---|---|---|
| Italian | [VoxCPM2](https://huggingface.co/openbmb/VoxCPM2), cloned from `voices/voxcpm2_it_ref.wav` so every chapter has the same narrator | Apache 2.0 |
| English | [Qwen3-TTS 1.7B CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice), speaker *Aiden*, run with [faster-qwen3-tts](https://pypi.org/project/faster-qwen3-tts/) | Apache 2.0 |

They were chosen in a blind listening test against Piper, Kokoro, Chatterbox, Google's phone
voices and others. To change a voice, create `<home>/server-data/voices.json`:

```json
{
  "it": { "voice": "D:\\voices\\my_narrator.wav", "label": "My narrator" },
  "en": { "speaker": "ryan", "label": "Qwen3-TTS · Ryan" }
}
```

A cloned voice needs 10–15 s of one clear speaker, no music. Qwen3-TTS speakers: aiden, dylan,
eric, ono_anna, ryan, serena, sohee, uncle_fu, vivian. A new voice means new narrations;
finished ones are kept. The same text with the same voice is never narrated twice: the
finished result is reused.

A voice can also use another model of the same family, with `"model"` (its Hugging Face id):

```json
{
  "en": { "model": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", "label": "Qwen3-TTS 0.6B · Aiden" }
}
```

A smaller model fits a smaller GPU; a different one means new narrations, as above. The models
must load with the same library as the voice they replace (VoxCPM for Italian, faster-qwen3-tts
for English). Only the models in the table have been tried; the 0.6B one above is an untested
example. `tools/prefetch.py` downloads only the models in the table.

The included Italian voice sample was generated by VoxCPM2 itself; it is not a recording of a
real person.

## Settings (environment variables)

`RACCONTAMI_TLS=0` turns the encrypted link off (plain HTTP); `RACCONTAMI_HOST` and `RACCONTAMI_PORT` set where the server listens (default `0.0.0.0` and `8765`).

| Variable | Default | |
|---|---|---|
| `RACCONTAMI_HOME` | `~/raccontami` | home folder for everything below |
| `RACCONTAMI_DATA` | `<home>/server-data` | jobs, token, log, voices.json |
| `RACCONTAMI_MODELS` | `<home>/models` | downloaded models |
| `RACCONTAMI_ONNX` | `<home>/onnx` | phone models |
| `RACCONTAMI_TTS` | `<home>/tts` | voice environments `env-a` (VoxCPM2), `env-c` (Qwen3-TTS) |
| `RACCONTAMI_CACHE` | `<tts>/cache` | compiled voice kernels |
| `RACCONTAMI_TOKEN` | random, saved in token.txt | the app's password |
| `RACCONTAMI_NAME` | computer name | how the app names this server |
| `RACCONTAMI_FIRST_PART_S` | 600 | maximum length of a narration's first part, in seconds |
| `RACCONTAMI_ONE_JOB` | off | `1`: syncs and narrations take turns on the GPU (for GPUs under 12 GB, see Requirements) |
| `RACCONTAMI_WHISPER_MODEL` | `turbo` | Whisper model for syncs: `small` or `medium` for less graphics memory, `large-v3` for a little more accuracy, several times slower. It only places the anchors (the word times come from wav2vec2), so turbo is enough on any GPU that fits it. Applies to audiobooks synced from then on; books already synced keep their result |

## Troubleshooting

| You see | Why, and what to do |
|---|---|
| The first narration of a language "prepares the voice" for 3–4 min | VoxCPM2 is compiling; the result is cached, later starts take under a minute |
| Narration below 1× real time | on Windows, `triton-windows` is missing in `tts\env-a` (re-run the installer); or the GPU is busy |
| `property 'upsample' ... has no setter` | wrong transformers in `env-c`: `pip install transformers==5.15.1` |
| The app can't reach the server | firewall, wrong address, or another network; the address in a phone browser should answer `{"detail":"bad token"}` |
| A narration failed | `<home>/server-data/jobs/<id>/narrate.log`; Retry in the app keeps finished paragraphs |
| Disk filling up | delete folders in `<home>/server-data/jobs/` for books already on the phone |

## How it works

- **Sync**: Whisper (turbo unless `RACCONTAMI_WHISPER_MODEL` says otherwise) transcribes the audiobook, a matcher finds where the book's words and
  the transcript agree, and wav2vec2 CTC forced alignment times every word between those anchors.
  Scanned-book recognition errors are detected along the way (the narrator says the right word).
- **Narrate**: the text is cut into paragraphs (long ones at sentence ends); a worker in the voice's
  own environment speaks each one at low CPU priority, saving it as soon as it is done; each is
  aligned with its words right away, and a paragraph that does not match the text is read again
  once. Parts and the final file are AAC with the usual sync file.

The API the app uses is described in [docs/api.md](docs/api.md).

Tested on Windows 11 with an RTX 5080. The Linux installer and the Docker image follow the
same steps but have not been run on real hardware yet; reports welcome.

## Licence

Apache 2.0, see [LICENSE](LICENSE). The models are downloaded from their authors under their own
licences, all free for commercial use: Whisper (MIT), wav2vec2 aligners (Apache 2.0), VoxCPM2
(Apache 2.0), Qwen3-TTS (Apache 2.0).
