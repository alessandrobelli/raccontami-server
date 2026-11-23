"""Downloads the models the server's languages need, so the first sync or narration does not wait for
the downloads. Safe to run again: finished files are skipped.

  python tools/prefetch.py

The languages are the server's (RACCONTAMI_LANGUAGES, English and Italian without it): their word-timing
models, their voice models (raccontami_sync/languages.py) and Whisper.
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from raccontami_sync import aligners, languages  # noqa: E402
from raccontami_sync.paths import MODELS, model_homes  # noqa: E402

# the same folders the server uses, so what is downloaded here is found there
os.environ.update(model_homes(os.environ, MODELS))

os.environ.setdefault("OMP_NUM_THREADS", "2")  # the word-timing models are loaded once below, on the processor
# the installer's window keeps the download bars, without notes that change nothing (no symlinks, no account,
# weights used only in training)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")  # no usage reports to Hugging Face (README, Privacy)
# the same files the server loads: without this, a model with only the older weight format makes the loader
# fetch a converted copy in the background, 1.3 GB more, unfinished when this script ends (the server sets it too)
os.environ.setdefault("DISABLE_SAFETENSORS_CONVERSION", "1")
logging.getLogger("torch.distributed.elastic.multiprocessing.redirects").setLevel(logging.ERROR)  # a note that changes nothing

from huggingface_hub import snapshot_download  # noqa: E402

LANGS = languages.enabled(os.environ)
REPOS = languages.downloads(LANGS)
ALIGNERS = {languages.LANGUAGES[lang]["aligner"] for lang in LANGS}

total = len(REPOS) + 1  # and Whisper, below
for at, repo in enumerate(REPOS, 1):
    print(f"model {at} of {total}: {repo}", flush=True)
    if repo in ALIGNERS:
        aligners.fetch(repo)  # only the files the server loads (its repository may hold 3.6 GB more)
    else:
        snapshot_download(repo)

import whisper  # noqa: E402

from raccontami_sync.pipeline import WHISPER_MODEL  # noqa: E402  (RACCONTAMI_WHISPER_MODEL, default turbo)

if WHISPER_MODEL in whisper._MODELS:  # a model file given by its path needs no download
    print(f"model {total} of {total}: whisper {WHISPER_MODEL}", flush=True)
    whisper._download(whisper._MODELS[WHISPER_MODEL], str(MODELS / "whisper"), in_memory=False)
print("all models ready")
