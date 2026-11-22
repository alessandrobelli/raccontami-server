#!/usr/bin/env bash
# Installs the Raccontami server on Linux with an NVIDIA GPU. Safe to run again:
# whatever is already installed is kept, only what is missing is added.
#
#   RACCONTAMI_HOME=/srv/raccontami ./install/install-linux.sh [--skip-models] [--phone-models] [--service]
#
# The models (about 20 GB) go to $RACCONTAMI_HOME/models, or to RACCONTAMI_MODELS=/big/disk/models given
# the same way; a folder chosen so is kept in settings.txt, and a later run uses the one written there.
#
# --phone-models also builds the phone models here: a second source, the app downloads them from GitHub
# (README, "Phone models"). --skip-phone-models, the usual now, is still accepted.
#
# Needs: python3.12 with venv, ffmpeg, an NVIDIA driver for CUDA 12.8 (570+).
# --service writes and enables a systemd service (asks for sudo).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
H="${RACCONTAMI_HOME:-$HOME/raccontami}"
TORCH_INDEX=https://download.pytorch.org/whl/cu128
SKIP_MODELS=0; PHONE=0; SERVICE=0
for a in "$@"; do case "$a" in
  --skip-models) SKIP_MODELS=1;; --phone-models) PHONE=1;; --skip-phone-models) PHONE=0;; --service) SERVICE=1;;
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
H="$(realpath -m "$H")"
SETTINGS="$H/settings.txt"
models_setting() {  # the models folder settings.txt names, read as the server reads it, or nothing
  [ -f "$1" ] || return 0
  sed -n -E 's/^[[:space:]]*RACCONTAMI_MODELS[[:space:]]*=(.*)$/\1/p' "$1" |
    sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s/^"+//; s/"+$//' | grep -v '^$' | tail -n 1 || true
}
# the folder the models download into must be the one the server reads, so settings.txt wins: the
# installer does not change a line that is already there
named="$(models_setting "$SETTINGS")"
if [ -n "$named" ]; then
  M="$named"
  if [ -n "${RACCONTAMI_MODELS:-}" ] && [ "$(realpath -m "$RACCONTAMI_MODELS")" != "$(realpath -m "$named")" ]; then
    echo "settings.txt already puts the models in $named, so they stay there. To move them, stop the server, move the folder and change RACCONTAMI_MODELS in settings.txt."
  fi
elif [ -n "${RACCONTAMI_MODELS:-}" ]; then
  M="$(realpath -m "$RACCONTAMI_MODELS")"
else
  M="$H/models"
fi
mkdir -p "$M"
echo "Home folder: $H"
echo "Models:      $M"
# a chosen folder holds every model, as the server does (raccontami_sync/paths.py, model_homes); without
# one, a HF_HOME set here keeps the Hugging Face models, nearly all of the 20 GB
chosen=0
{ [ -n "$named" ] || [ "$(realpath -m "$M")" != "$H/models" ]; } && chosen=1
[ -z "${HF_HOME:-}" ] || [ "$chosen" = 1 ] || echo "             (the Hugging Face models go to $HF_HOME instead: HF_HOME is set here)"
if [ "$(realpath -m "$M")" != "$H/models" ] && [ -n "$(ls -A "$H/models" 2>/dev/null)" ]; then
  echo "The models already in $H/models stay there and are not used: delete that folder to free its space."
fi
if [ ! -x "$H/env/bin/python" ]; then
  existing() { p="$1"; while [ ! -e "$p" ]; do p="$(dirname "$p")"; done; echo "$p"; }
  free_gb() { df -Pk "$1" | awk 'NR==2 {print int($4 / 1048576)}'; }
  device() { df -P "$1" | awk 'NR==2 {print $1}'; }
  if [ -n "${HF_HOME:-}" ] && [ "$chosen" = 0 ]; then hf="$(existing "$HF_HOME")"; else hf="$M"; fi
  if [ "$(device "$H")" = "$(device "$hf")" ]; then
    [ "$(free_gb "$H")" -ge 35 ] || fail "A new install needs about 35 GB (15 GB of Python environments, 20 GB of models) on the drive of $H and it has $(free_gb "$H") GB free. Free some space, or choose other folders with RACCONTAMI_HOME and RACCONTAMI_MODELS."
  else
    [ "$(free_gb "$H")" -ge 15 ] || fail "The Python environments need about 15 GB on the drive of $H and it has $(free_gb "$H") GB free. Free some space, or set RACCONTAMI_HOME to another drive."
    [ "$(free_gb "$hf")" -ge 20 ] || fail "The models need about 20 GB on the drive of $hf and it has $(free_gb "$hf") GB free. Free some space, or set RACCONTAMI_MODELS to another drive."
  fi
  printf '\nThis installs into %s, with the models in %s, and downloads about 35 GB.\nIt can be stopped and run again: what is already there is kept.\n' "$H" "$M"
fi
mkdir -p "$H"/{server-data,onnx,tts}
export PIP_DISABLE_PIP_VERSION_CHECK=1 RACCONTAMI_HOME="$H"
# the model download and the phone models do not read settings.txt: they are told the folder only when one
# was chosen, so that without one they follow a HF_HOME set here, as the server does
if [ "$chosen" = 1 ]; then export RACCONTAMI_MODELS="$M"; else unset RACCONTAMI_MODELS; fi

# the settings file is written before anything downloads, so a run stopped halfway and started again
# finds the models folder it chose
if [ ! -f "$SETTINGS" ]; then
  cat > "$SETTINGS" <<'EOS'
# Settings of the Raccontami server: one per line, NAME=value. Lines starting with # are notes.
# The installer only adds the models folder chosen when installing; it changes nothing else here.
# The README lists every setting.
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
      grep -E '^export RACCONTAMI_(NAME|TLS|ONE_JOB)=' "$H/start-server.sh" | sed -e 's/^export //' -e 's/"//g'; } >> "$SETTINGS"
    echo "settings kept from the earlier start file"
  fi
fi
if [ "$(realpath -m "$M")" != "$H/models" ] && [ -z "$(models_setting "$SETTINGS")" ]; then
  printf '\n# Where the models are, chosen when installing. To move them: stop the server, move the folder, change this line.\nRACCONTAMI_MODELS=%s\n' "$M" >> "$SETTINGS"
fi

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
if [ "$PHONE" = 0 ]; then
  printf '\nPhone models: not built here. The app downloads them from GitHub; --phone-models builds them here too.\n'
else
  step "Phone models (a second source for the app, which downloads them from GitHub first)"
  for m in facebook/wav2vec2-base-960h jonatasgrosman/wav2vec2-large-xlsr-53-italian; do
    n="${m##*/}"
    if [ -f "$H/onnx/$n.int8.onnx" ]; then echo "$n: already there"; else "$H/env/bin/python" "$REPO/tools/export_phone_model.py" "$m" "$H/onnx"; fi
  done
fi

step "Settings and start script"
echo "$SETTINGS"
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
