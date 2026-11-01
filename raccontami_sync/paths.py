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
