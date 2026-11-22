"""Where the server keeps its files. Everything lives under one home folder
(RACCONTAMI_HOME, default ~/raccontami); each part can also be moved alone.

  <home>/server-data   jobs, token.txt, server.log, voices.json   RACCONTAMI_DATA
  <home>/models        downloaded models (Hugging Face, Whisper)   RACCONTAMI_MODELS
  <home>/onnx          phone models served to the app               RACCONTAMI_ONNX
  <home>/tts           voice environments (env-a, env-c) + cache    RACCONTAMI_TTS
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("RACCONTAMI_HOME", Path.home() / "raccontami")).expanduser()
DATA = Path(os.environ.get("RACCONTAMI_DATA", HOME / "server-data"))
MODELS = Path(os.environ.get("RACCONTAMI_MODELS", HOME / "models"))
ONNX = Path(os.environ.get("RACCONTAMI_ONNX", HOME / "onnx"))
TTS = Path(os.environ.get("RACCONTAMI_TTS", HOME / "tts"))
# compiled voice kernels: the first start of a voice takes minutes, later ones seconds
CACHE = Path(os.environ.get("RACCONTAMI_CACHE", TTS / "cache"))
VOICES = REPO / "voices"


def model_homes(env, models: Path) -> dict[str, str]:
    """HF_HOME and TORCH_HOME, where the libraries download their models. A models folder that was
    chosen (RACCONTAMI_MODELS, where the server is started or in settings.txt) holds them whatever the
    computer sets. Without one, a HF_HOME or TORCH_HOME already set on the computer is kept: its
    models may be there already. Else they go in the models folder."""
    chosen = bool(env.get("RACCONTAMI_MODELS"))
    return {name: str(models / sub) if chosen or not env.get(name) else env[name]
            for name, sub in (("HF_HOME", "hf"), ("TORCH_HOME", "torch"))}
