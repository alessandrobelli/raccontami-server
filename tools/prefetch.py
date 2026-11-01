"""Downloads every model the server uses, so the first sync or narration does not
wait for ~20 GB of downloads. Safe to run again: finished files are skipped.

  python tools/prefetch.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from raccontami_sync.paths import MODELS  # noqa: E402

os.environ.setdefault("HF_HOME", str(MODELS / "hf"))

from huggingface_hub import snapshot_download  # noqa: E402

REPOS = [
    "facebook/wav2vec2-large-960h-lv60-self",          # English alignment
    "jonatasgrosman/wav2vec2-large-xlsr-53-italian",   # Italian alignment
    "openbmb/VoxCPM2",                                 # Italian narration
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",            # English narration
]

for repo in REPOS:
    print("model", repo, flush=True)
    snapshot_download(repo)

print("model whisper turbo", flush=True)
import whisper  # noqa: E402

whisper._download(whisper._MODELS["turbo"], str(MODELS / "whisper"), in_memory=False)
print("all models ready")
