#!/usr/bin/env bash
# Installs the Raccontami server on Linux with an NVIDIA GPU. Safe to run again:
# whatever is already installed is kept, only what is missing is added.
#
#   RACCONTAMI_HOME=/srv/raccontami ./install/install-linux.sh [--skip-models] [--skip-phone-models] [--service]
#
# Needs: python3.12 with venv, ffmpeg, an NVIDIA driver for CUDA 12.8 (570+).
# --service writes and enables a systemd service (asks for sudo).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
H="${RACCONTAMI_HOME:-$HOME/raccontami}"
TORCH_INDEX=https://download.pytorch.org/whl/cu128
SKIP_MODELS=0; SKIP_PHONE=0; SERVICE=0
for a in "$@"; do case "$a" in
  --skip-models) SKIP_MODELS=1;; --skip-phone-models) SKIP_PHONE=1;; --service) SERVICE=1;;
  *) echo "unknown option $a"; exit 2;; esac; done
step() { printf '\n== %s\n' "$1"; }
fail() { printf '\n%s\n' "$1" >&2; exit 1; }

step "Checking the computer"
command -v python3.12 >/dev/null || fail "python3.12 not found (e.g. apt install python3.12 python3.12-venv)."
command -v ffmpeg >/dev/null || fail "ffmpeg not found (e.g. apt install ffmpeg)."
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || fail "No NVIDIA GPU found (nvidia-smi)."
# the voices need CUDA 12.8, which drivers before 570 do not have: found now, not after 35 GB of downloads
driver="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n 1 | cut -d. -f1)"
case "$driver" in ''|*[!0-9]*) driver=0;; esac
[ "$driver" -eq 0 ] || [ "$driver" -ge 570 ] || fail "The NVIDIA driver is version $driver; the server needs 570 or newer."

mkdir -p "$H"
free_gb="$(df -Pk "$H" | awk 'NR==2 {print int($4 / 1048576)}')"
echo "Free space on the drive of $H: ${free_gb} GB"
if [ ! -x "$H/env/bin/python" ]; then
  [ "$free_gb" -ge 35 ] || fail "A new install needs about 35 GB (15 GB of Python environments, 20 GB of models) and this drive has ${free_gb} GB free. Free some space, or set RACCONTAMI_HOME to another drive."
  printf '\nThis installs everything into %s and downloads about 35 GB.\nIt can be stopped and run again: what is already there is kept.\n' "$H"
fi
mkdir -p "$H"/{server-data,models,onnx,tts}
export PIP_DISABLE_PIP_VERSION_CHECK=1 RACCONTAMI_HOME="$H"

ensure_env() {  # dir requirements label
  step "Python environment: $3 ($1)"
  [ -x "$1/bin/python" ] || python3.12 -m venv "$1"
  if "$1/bin/python" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() and torch.__version__.startswith('2.11') else 1)" 2>/dev/null; then
    echo "PyTorch with CUDA: already there"
  else
    echo "installing PyTorch with CUDA (about 3 GB)..."
    "$1/bin/pip" install torch==2.11.0 torchaudio==2.11.0 --index-url "$TORCH_INDEX"
  fi
  echo "installing the other packages (a few minutes, nothing is shown meanwhile)..."
  "$1/bin/pip" install -q -r "$REPO/$2"
  echo ok
}
ensure_env "$H/env" requirements.txt "server"
ensure_env "$H/tts/env-a" requirements-voxcpm.txt "Italian voice (VoxCPM2)"
ensure_env "$H/tts/env-c" requirements-qwen.txt "English voice (Qwen3-TTS)"

if [ "$SKIP_MODELS" = 0 ]; then
  step "Downloading the models (about 20 GB the first time)"
  "$H/env/bin/python" "$REPO/tools/prefetch.py"
fi
if [ "$SKIP_PHONE" = 0 ]; then
  step "Phone models (for syncing on the phone without this computer)"
  for m in facebook/wav2vec2-base-960h jonatasgrosman/wav2vec2-large-xlsr-53-italian; do
    n="${m##*/}"
    if [ -f "$H/onnx/$n.int8.onnx" ]; then echo "$n: already there"; else "$H/env/bin/python" "$REPO/tools/export_phone_model.py" "$m" "$H/onnx"; fi
  done
fi

step "Settings and start script"
if [ ! -f "$H/settings.txt" ]; then
  cat > "$H/settings.txt" <<'EOS'
# Settings of the Raccontami server: one per line, NAME=value. Lines starting with # are notes.
# The installer never changes this file. The README lists every setting.
# The server reads it when it starts: restart the server after a change.

# How the app names this server
# RACCONTAMI_NAME=My server

# Plain HTTP instead of the encrypted link (behind a proxy, or for an older app)
# RACCONTAMI_TLS=0

# GPU under 12 GB: run syncs and narrations one at a time
# RACCONTAMI_ONE_JOB=1
EOS
  # settings written into a start file made by an earlier version move here, so they are not lost
  if [ -f "$H/start-server.sh" ] && grep -Eq '^export RACCONTAMI_(NAME|TLS|ONE_JOB)=' "$H/start-server.sh"; then
    { echo; echo "# Kept from the earlier start file"
      grep -E '^export RACCONTAMI_(NAME|TLS|ONE_JOB)=' "$H/start-server.sh" | sed -e 's/^export //' -e 's/"//g'; } >> "$H/settings.txt"
    echo "settings kept from the earlier start file"
  fi
fi
echo "$H/settings.txt"
cat > "$H/start-server.sh" <<EOS
#!/usr/bin/env bash
# Starts the Raccontami server (port 8765). Made by install-linux.sh, which writes it anew at every
# run: settings go in settings.txt beside this file, not here.
export RACCONTAMI_HOME="$H" PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
cd "$REPO"
exec "$H/env/bin/python" -m raccontami_sync.serve
EOS
chmod +x "$H/start-server.sh"
echo "$H/start-server.sh"

if [ "$SERVICE" = 1 ]; then
  step "systemd service"
  sudo tee /etc/systemd/system/raccontami.service >/dev/null <<EOS
[Unit]
Description=Raccontami server
After=network-online.target

[Service]
User=$(id -un)
ExecStart=$H/start-server.sh
Restart=always
Nice=10

[Install]
WantedBy=multi-user.target
EOS
  sudo systemctl daemon-reload && sudo systemctl enable --now raccontami
  echo "running: journalctl -u raccontami -f shows its log (and the token for the app)"
fi

step "Done"
echo "Start the server: $H/start-server.sh  (it prints the address, the token and the code the app asks for)"
echo "Settings:         $H/settings.txt"
