# Raccontami server for rented GPU machines (RunPod, Vast.ai, Lambda, ...).
#   docker build -f docker/Dockerfile -t raccontami-server .
#   docker run --gpus all -p 8765:8765 -v raccontami-data:/data raccontami-server
# Everything that must survive a restart (jobs, token, models, compiled voice cache)
# lives in /data: mount a persistent volume there, or narrations start over.
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
    PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3-pip python3.12-dev build-essential ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# PyTorch once, shared by the three environments (they see it through --system-site-packages)
RUN pip install --break-system-packages torch==2.11.0 torchaudio==2.11.0 \
        --index-url https://download.pytorch.org/whl/cu128

WORKDIR /opt/raccontami/server
COPY requirements*.txt ./
RUN python3.12 -m venv --system-site-packages /opt/raccontami/env \
 && /opt/raccontami/env/bin/pip install -r requirements.txt \
 && python3.12 -m venv --system-site-packages /opt/raccontami/tts/env-a \
 && /opt/raccontami/tts/env-a/bin/pip install -r requirements-voxcpm.txt \
 && python3.12 -m venv --system-site-packages /opt/raccontami/tts/env-c \
 && /opt/raccontami/tts/env-c/bin/pip install -r requirements-qwen.txt
COPY . .

ENV RACCONTAMI_HOME=/data RACCONTAMI_TTS=/opt/raccontami/tts RACCONTAMI_CACHE=/data/cache
EXPOSE 8765
CMD ["bash", "docker/entrypoint.sh"]
