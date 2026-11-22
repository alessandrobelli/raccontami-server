#!/usr/bin/env bash
# First start: downloads the models (~20 GB) into /data. Later starts find them there and start in seconds.
# With RACCONTAMI_PHONE_MODELS=1 it also builds the phone models, a second source for the app, which
# downloads them from GitHub (README, "Phone models").
set -e
mkdir -p /data/onnx
PY=/opt/raccontami/env/bin/python
if [ ! -f /data/.models-ready ]; then
  "$PY" tools/prefetch.py && touch /data/.models-ready
fi
if [ "${RACCONTAMI_PHONE_MODELS:-0}" = 1 ]; then
  for m in facebook/wav2vec2-base-960h jonatasgrosman/wav2vec2-large-xlsr-53-italian; do
    [ -f "/data/onnx/${m##*/}.int8.onnx" ] || "$PY" tools/export_phone_model.py "$m" /data/onnx || true
  done
fi
exec "$PY" -m raccontami_sync.serve
