<#
.SYNOPSIS
  Installs the Raccontami server on Windows with an NVIDIA GPU. Safe to run again:
  whatever is already installed is kept, only what is missing is added.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\install-windows.ps1 -RaccontamiHome D:\raccontami

  Needs: Python 3.12 (py launcher), ffmpeg on PATH, an NVIDIA driver for CUDA 12.8 (570+).
  Disk: about 15 GB of Python environments + 20 GB of models in the home folder.
#>
param(
    [string]$RaccontamiHome = "$env:USERPROFILE\raccontami",
    [switch]$SkipModels,        # do not download the models now (they download on first use)
    [switch]$SkipPhoneModels    # do not build the models the app downloads for syncing on the phone
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$H = $RaccontamiHome
$TorchIndex = "https://download.pytorch.org/whl/cu128"

function Step($m) { Write-Host "`n== $m" -ForegroundColor Cyan }
function Fail($m) { Write-Host "`n$m" -ForegroundColor Red; exit 1 }

Step "Checking the computer"
try { $py = (& py -3.12 -c "import sys; print(sys.executable)") } catch { $py = $null }
if (-not $py) { Fail "Python 3.12 not found. Install it from python.org (tick 'Add to PATH'), then run this again." }
Write-Host "Python 3.12: $py"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Fail "ffmpeg not found. Install it (winget install Gyan.FFmpeg), open a new terminal and run this again."
}
Write-Host "ffmpeg: ok"
try { $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader) } catch { $gpu = $null }
if (-not $gpu) { Fail "No NVIDIA GPU found (nvidia-smi). Install the latest NVIDIA driver." }
Write-Host "GPU: $gpu"

New-Item -ItemType Directory -Force $H, "$H\server-data", "$H\models", "$H\onnx", "$H\tts" | Out-Null
$env:PIP_CACHE_DIR = "$H\pip-cache"     # keeps the multi-GB downloads off C:
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:RACCONTAMI_HOME = $H

function Ensure-Env($dir, $requirements, $label) {
    Step "Python environment: $label ($dir)"
    $python = "$dir\Scripts\python.exe"
    if (-not (Test-Path $python)) { & py -3.12 -m venv $dir; if ($LASTEXITCODE) { Fail "Could not create $dir" } }
    & $python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() and torch.__version__.startswith('2.11') else 1)" 2>$null
    if ($LASTEXITCODE) {
        Write-Host "installing PyTorch with CUDA (about 3 GB)..."
        & $python -m pip install -q torch==2.11.0 torchaudio==2.11.0 --index-url $TorchIndex
        if ($LASTEXITCODE) { Fail "PyTorch install failed in $dir" }
    } else { Write-Host "PyTorch with CUDA: already there" }
    & $python -m pip install -q -r "$Repo\$requirements"
    if ($LASTEXITCODE) { Fail "Installing $requirements failed in $dir" }
    Write-Host "ok"
    return $python
}

$serverPy = Ensure-Env "$H\env" "requirements.txt" "server"
Ensure-Env "$H\tts\env-a" "requirements-voxcpm.txt" "Italian voice (VoxCPM2)" | Out-Null
Ensure-Env "$H\tts\env-c" "requirements-qwen.txt" "English voice (Qwen3-TTS)" | Out-Null

if (-not $SkipModels) {
    Step "Downloading the models (about 20 GB the first time)"
    & $serverPy "$Repo\tools\prefetch.py"
    if ($LASTEXITCODE) { Fail "Model download failed; run this again to continue where it stopped." }
}

if (-not $SkipPhoneModels) {
    Step "Phone models (for syncing on the phone without this computer)"
    foreach ($m in "facebook/wav2vec2-base-960h", "jonatasgrosman/wav2vec2-large-xlsr-53-italian") {
        $name = $m.Split("/")[1]
        if (Test-Path "$H\onnx\$name.int8.onnx") { Write-Host "$name`: already there"; continue }
        & $serverPy "$Repo\tools\export_phone_model.py" $m "$H\onnx"
        if ($LASTEXITCODE) { Fail "Building the phone model $name failed." }
    }
}

Step "Start script"
$start = "$H\start-server.bat"
@"
@echo off
rem Starts the Raccontami server (port 8765). Made by install-windows.ps1; run that again to update it.
title Raccontami server
set RACCONTAMI_HOME=$H
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
rem set RACCONTAMI_NAME=My PC
rem Plain HTTP instead of the encrypted link (behind a proxy, or for an older app)
rem set RACCONTAMI_TLS=0
rem GPU under 12 GB: run syncs and narrations one at a time
rem set RACCONTAMI_ONE_JOB=1
cd /d "$Repo"
"$serverPy" -m raccontami_sync.serve
echo.
echo The server stopped. Press a key to close this window.
pause > nul
"@ | Set-Content -Encoding ascii $start
Write-Host $start

Remove-Item -Recurse -Force "$H\pip-cache" -ErrorAction SilentlyContinue

Step "Done"
Write-Host @"
Start the server:   double-click $start
                    (its window shows the token to type into the app)

Let phones on your network reach it (run once, as administrator):
  New-NetFirewallRule -DisplayName "Raccontami 8765" -Direction Inbound -Protocol TCP -LocalPort 8765 -RemoteAddress LocalSubnet -Action Allow

Start it at login (so narrations resume after a restart):
  Win+R -> shell:startup -> New > Shortcut -> $start -> Properties: Run minimized
"@
