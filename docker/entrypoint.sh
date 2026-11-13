#!/usr/bin/env bash
# First start: downloads the models (~20 GB) and builds the phone models into /data.
# Later starts find them there and start in seconds.
set -e
mkdir -p /data/onnx
PY=/opt/raccontami/env/bin/python
if [ ! -f /data/.models-ready ]; then
  "$PY" tools/prefetch.py && touch /data/.models-ready
fi
for m in facebook/wav2vec2-base-960h jonatasgrosman/wav2vec2-large-xlsr-53-italian; do
  [ -f "/data/onnx/${m##*/}.int8.onnx" ] || "$PY" tools/export_phone_model.py "$m" /data/onnx || true
done
exec "$PY" -m raccontami_sync.serve
