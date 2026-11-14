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
    [switch]$SkipPhoneModels,   # do not build the models the app downloads for syncing on the phone
    [switch]$NoQuestions        # do not ask about the firewall and starting at login (the last lines say how)
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
# the voices need CUDA 12.8, which drivers before 570 do not have: found now, not after 35 GB of downloads
$driver = 0
if (@($gpu)[0] -match ',\s*(\d+)\.[\d.]+\s*$') { $driver = [int]$Matches[1] }
if ($driver -and $driver -lt 570) {
    Fail "The NVIDIA driver is version $driver; the server needs 570 or newer. Update it from nvidia.com (or the NVIDIA app), then run this again."
}

New-Item -ItemType Directory -Force $H | Out-Null
$fresh = -not (Test-Path "$H\env\Scripts\python.exe")
$freeGB = [math]::Floor(([System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot((Resolve-Path $H).Path))).AvailableFreeSpace / 1GB)
Write-Host "Free space on the drive of ${H}: $freeGB GB"
if ($fresh) {
    if ($freeGB -lt 35) {
        Fail "A new install needs about 35 GB (15 GB of Python environments, 20 GB of models) and this drive has $freeGB GB free. Free some space, or choose another drive with -RaccontamiHome."
    }
    Write-Host @"

This installs everything into $H
and downloads about 35 GB: three Python environments (about 15 GB) and the models (about 20 GB).
On a fast connection that is around half an hour; on a slow one it can take hours. It can be
stopped and run again: what is already there is kept.
"@
}

New-Item -ItemType Directory -Force "$H\server-data", "$H\models", "$H\onnx", "$H\tts" | Out-Null
$env:PIP_CACHE_DIR = "$H\pip-cache"     # keeps the multi-GB downloads off C:
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:RACCONTAMI_HOME = $H

function Ensure-Env($dir, $requirements, $label) {
    Step "Python environment: $label ($dir)"
    $python = "$dir\Scripts\python.exe"
    if (-not (Test-Path $python)) { & py -3.12 -m venv $dir; if ($LASTEXITCODE) { Fail "Could not create $dir" } }
    & $python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() and torch.__version__.startswith('2.11') else 1)" 2>$null
    if ($LASTEXITCODE) {
        Write-Host "installing PyTorch with CUDA (about 3 GB; the bar below shows the download)..."
        & $python -m pip install torch==2.11.0 torchaudio==2.11.0 --index-url $TorchIndex
        if ($LASTEXITCODE) { Fail "PyTorch install failed in $dir" }
    } else { Write-Host "PyTorch with CUDA: already there" }
    Write-Host "installing the other packages (a few minutes, nothing is shown meanwhile)..."
    & $python -m pip install -q -r "$Repo\$requirements"
    if ($LASTEXITCODE) { Fail "Installing $requirements failed in $dir" }
    Write-Host "ok"
}

# called without taking their output, so pip writes straight to the window and can draw its progress bar
$serverPy = "$H\env\Scripts\python.exe"
Ensure-Env "$H\env" "requirements.txt" "server"
Ensure-Env "$H\tts\env-a" "requirements-voxcpm.txt" "Italian voice (VoxCPM2)"
Ensure-Env "$H\tts\env-c" "requirements-qwen.txt" "English voice (Qwen3-TTS)"

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

Step "Settings and start script"
$start = "$H\start-server.bat"
$settings = "$H\settings.txt"
if (-not (Test-Path $settings)) {
    # settings written into a start file made by an earlier version move here, so they are not lost
    $kept = @()
    if (Test-Path $start) {
        $kept = @(Get-Content $start | Where-Object { $_ -match '^\s*set\s+(RACCONTAMI_(?!HOME=)\w+=.+)$' } |
                  ForEach-Object { $Matches[1].Trim() })
    }
    @"
# Settings of the Raccontami server: one per line, NAME=value. Lines starting with # are notes.
# The installer never changes this file. The README lists every setting.
# The server reads it when it starts: stop the server and start it again after a change.

# How the app names this server
# RACCONTAMI_NAME=My PC

# Plain HTTP instead of the encrypted link (behind a proxy, or for an older app)
# RACCONTAMI_TLS=0

# GPU under 12 GB: run syncs and narrations one at a time
# RACCONTAMI_ONE_JOB=1
"@ | Set-Content -Encoding utf8 $settings
    if ($kept) {
        Add-Content -Encoding utf8 $settings (@("", "# Kept from the earlier start file") + $kept)
        Write-Host "settings kept from the earlier start file: $($kept -join ', ')"
    }
}
Write-Host $settings
@"
@echo off
rem Starts the Raccontami server (port 8765). Made by install-windows.ps1, which writes it anew at
rem every run: settings go in settings.txt beside this file, not here.
title Raccontami server
set RACCONTAMI_HOME=$H
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "$Repo"
"$serverPy" -m raccontami_sync.serve
echo.
echo The server stopped. Press a key to close this window.
pause > nul
"@ | Set-Content -Encoding ascii $start
Write-Host $start

# the same server without a window: it lives next to the clock (see raccontami_sync/background.py)
$hidden = "$H\Raccontami server (no window).lnk"
$link = (New-Object -ComObject WScript.Shell).CreateShortcut($hidden)
$link.TargetPath = (Join-Path (Split-Path $serverPy) "pythonw.exe")
$link.Arguments = "-m raccontami_sync.background --home `"$H`""
$link.WorkingDirectory = "$Repo"
$link.Description = "Starts the Raccontami server without a window; its icon next to the clock stops it"
$link.Save()
Write-Host $hidden

Remove-Item -Recurse -Force "$H\pip-cache" -ErrorAction SilentlyContinue

function Ask($question) {
    # nobody to ask (run from another script): the answer is no, and the lines at the end say how to do it later
    if ($NoQuestions -or -not [Environment]::UserInteractive) { return $false }
    return (Read-Host "$question [y/N]").Trim() -match '^(y|yes|s|si)$'
}

Step "Your network"
$ruleName = "Raccontami 8765"
$ruleCommand = "New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Protocol TCP -LocalPort 8765 -RemoteAddress LocalSubnet -Action Allow"
$ruleThere = [bool](Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)
if ($ruleThere) {
    Write-Host "Windows firewall: phones on your network can already reach the server"
} elseif (Ask "Let phones on your home network reach the server? Windows will ask for an administrator's permission.") {
    try {
        # the rule needs an administrator: only this one line is run as one
        Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "-NoProfile", "-Command", $ruleCommand
        $ruleThere = [bool](Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)
    } catch { $ruleThere = $false }
    Write-Host $(if ($ruleThere) { "Windows firewall: rule added (port 8765, from your own network only)" }
                 else { "Windows firewall: the rule was not added. The line to run later is below." })
}

$startup = [Environment]::GetFolderPath("Startup")
$atLogin = Test-Path (Join-Path $startup (Split-Path -Leaf $hidden))
if (-not $atLogin -and (Ask "Start the server by itself when you log in to Windows (without a window, next to the clock)?")) {
    Copy-Item $hidden $startup
    $atLogin = $true
    Write-Host "It will start at login. To undo: Win+R -> shell:startup -> delete the shortcut."
}

$startedNow = $false
if (Ask "Start the server now? Its window shows the address, the token and the code the app asks for.") {
    Start-Process $start
    $startedNow = $true
}

Step "Done"
if ($startedNow) { Write-Host "The server is starting in its own window. In the app: Settings, the server's settings, Search local network.`n" }
Write-Host @"
Start the server:   double-click $start
                    (its window shows the address, the token and the code the app asks for)
Without a window:   double-click $hidden
                    (it lives next to the clock, maybe behind the small arrow there: the icon opens its
                    page, shows how to connect the phone, puts work on hold and stops the server)
Settings:           $settings
"@
if (-not $ruleThere) {
    Write-Host @"

Phones cannot reach the server yet. Run this once, as administrator:
  $ruleCommand
"@
}
if ($atLogin) {
    Write-Host @"

Started at login it does not take the graphics card by itself: an unfinished narration waits on
hold, and the icon says so, until you continue it from the icon or the page.
"@
} else {
    Write-Host @"

To start it at login: Win+R -> shell:startup -> copy "$hidden" there.
Started that way it does not take the graphics card by itself: an unfinished narration waits on
hold, and the icon says so, until you continue it from the icon or the page.
"@
}
