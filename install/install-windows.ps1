<#
.SYNOPSIS
  Installs the Raccontami server on Windows with an NVIDIA GPU. Safe to run again:
  whatever is already installed is kept, only what is missing is added.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install\install-windows.ps1 -RaccontamiHome D:\raccontami

  Needs: Python 3.12 (py launcher), ffmpeg on PATH, an NVIDIA driver for CUDA 12.8 (570+).
  Disk: about 15 GB of Python environments in the home folder + 20 GB of models, in <home>\models or
  in the folder given with -ModelsDir (for example -ModelsDir E:\raccontami-models).
#>
param(
    [string]$RaccontamiHome = "$env:USERPROFILE\raccontami",
    [string]$ModelsDir,         # where the models go (about 20 GB); without it, <home>\models. Kept in settings.txt
    [switch]$SkipModels,        # do not download the models now (they download on first use)
    [switch]$PhoneModels,       # also build the phone models here: a second source, the app gets them from GitHub (README, "Phone models")
    [switch]$SkipPhoneModels,   # the usual now; still accepted so that older commands work
    [switch]$NoQuestions,       # do not ask about the firewall and starting at login (the last lines say how)
    [string]$Python             # the python.exe (3.12) to make the environments with; without it, the py launcher's
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$H = $RaccontamiHome
$TorchIndex = "https://download.pytorch.org/whl/cu128"

function Step($m) { Write-Host "`n== $m" -ForegroundColor Cyan }
function Fail($m) { Write-Host "`n$m" -ForegroundColor Red; exit 1 }

function Write-BatchFile($path, $text) {
    # A .bat that holds a folder name with an accent (C:\Users\Nicolo with a grave o): written as ASCII the
    # letter became ?, and cmd reads the file in whatever code page its window has. So the file is UTF-8
    # (without the mark, which cmd would take for a command) and its window switches to UTF-8 on the
    # second line, before any path is read. Windows line ends, as cmd expects.
    # (This script stays ASCII: Windows PowerShell reads a script without a BOM as ANSI.)
    $all = "@echo off`r`nchcp 65001 > nul`r`n" + ($text -replace "`r?`n", "`r`n") + "`r`n"
    [System.IO.File]::WriteAllText($path, $all, (New-Object System.Text.UTF8Encoding $false))
}

function Get-FullFolder($path) {
    # "D:\my folder\" handed on as an argument would end in \" and lose its closing quote; a drive's root keeps it.
    # Given that way by another program, it arrives with the quote inside (D:\my folder"), which is dropped here.
    $full = [System.IO.Path]::GetFullPath("$path".Trim().Trim('"'))
    if ($full.Length -gt 3) { $full = $full.TrimEnd('\') }
    $full
}

function Get-ModelsSetting($file) {
    # the models folder settings.txt names, read as the server reads it (raccontami_sync/settings.py), or nothing
    if (-not (Test-Path -LiteralPath $file)) { return "" }
    $found = ""
    foreach ($line in Get-Content -LiteralPath $file -Encoding UTF8) {
        if ($line -match '^\s*RACCONTAMI_MODELS\s*=(.*)$') {
            $value = $Matches[1].Trim().Trim('"')
            if ($value) { $found = $value }
        }
    }
    $found
}

function Resolve-ModelsFolder($file, $chosen, $usual) {
    # The folder the models download into must be the one the server reads, so settings.txt wins: the
    # installer does not change a line that is already there.
    $named = Get-ModelsSetting $file
    if ($named) {
        if ($chosen -and (Get-FullFolder $chosen) -ne (Get-FullFolder $named)) {
            Write-Host "settings.txt already puts the models in $named, so they stay there. To move them, stop the server, move the folder and change RACCONTAMI_MODELS in settings.txt."
        }
        return $named
    }
    if ($chosen) { return (Get-FullFolder $chosen) }
    $usual
}

function Add-ModelsSetting($file, $folder, $usual) {
    # a models folder chosen at install goes into settings.txt, which both starts read (with and without a window)
    if ((Get-FullFolder $folder) -eq (Get-FullFolder $usual) -or (Get-ModelsSetting $file)) { return }
    Add-Content -Encoding utf8 -LiteralPath $file @("", "# Where the models are, chosen when installing. To move them: stop the server, move the folder, change this line.", "RACCONTAMI_MODELS=$folder")
}

Step "Checking the computer"
$setupHint = "Or use the installer (Raccontami-Server-Setup.exe), which brings its own: see the README."
if ($Python) {
    # a Python of the server's own, given by the caller
    try { $py = (& $Python -c "import sys; print(sys.executable if sys.version_info[:2] == (3, 12) else '')") } catch { $py = $null }
    if (-not $py) { Fail "$Python is not a Python 3.12." }
} else {
    try { $py = (& py -3.12 -c "import sys; print(sys.executable)") } catch { $py = $null }
    if (-not $py) { Fail "Python 3.12 not found. Install it from python.org (tick 'Add to PATH'), then run this again. $setupHint" }
}
Write-Host "Python 3.12: $py"
# an ffmpeg brought by the installer (.exe) is in the home folder; the server looks there too when it starts
if (Test-Path "$H\tools\ffmpeg\bin\ffmpeg.exe") { $env:PATH = "$H\tools\ffmpeg\bin;$env:PATH" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Fail "ffmpeg not found. Install it (winget install Gyan.FFmpeg), open a new terminal and run this again. $setupHint"
}
Write-Host "ffmpeg: $((Get-Command ffmpeg).Source)"
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
$H = Get-FullFolder $H
$fresh = -not (Test-Path "$H\env\Scripts\python.exe")
$settings = "$H\settings.txt"
$usualModels = "$H\models"
# the server's own order: a RACCONTAMI_MODELS already set on this computer wins over settings.txt
$modelsFromEnv = $env:RACCONTAMI_MODELS
if ($modelsFromEnv) {
    $Models = $modelsFromEnv
    Write-Host "RACCONTAMI_MODELS is set on this computer, so the models go to $Models, where the server looks for them."
} else {
    $Models = Resolve-ModelsFolder $settings $ModelsDir $usualModels
}
try { New-Item -ItemType Directory -Force $Models -ErrorAction Stop | Out-Null }
catch { Fail "The models folder $Models cannot be made ($($_.Exception.Message)). Check the drive and the folder name, then run this again." }
# a chosen folder holds every model, as the server does (raccontami_sync/paths.py, model_homes); without
# one, a HF_HOME set on this computer keeps the Hugging Face models, nearly all of the 20 GB
$modelsChosen = [bool]($modelsFromEnv -or (Get-FullFolder $Models) -ne $usualModels -or (Get-ModelsSetting $settings))
Write-Host "Home folder: $H"
Write-Host "Models:      $Models"
if ($env:HF_HOME -and -not $modelsChosen) { Write-Host "             (the Hugging Face models go to $env:HF_HOME instead: HF_HOME is set on this computer)" }
if ((Get-FullFolder $Models) -ne $usualModels -and (Test-Path "$usualModels\*")) {
    Write-Host "The models already in $usualModels stay there and are not used: delete that folder to free its space."
}
if ($fresh) {
    # GB needed per drive: the Python environments in the home folder, the models where they go
    $need = [ordered]@{}
    foreach ($part in @($H, 15), @($(if ($env:HF_HOME -and -not $modelsChosen) { $env:HF_HOME } else { $Models }), 20)) {
        $root = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($part[0]))
        $need[$root] = $need[$root] + $part[1]
    }
    foreach ($root in $need.Keys) {
        $freeGB = [math]::Floor(([System.IO.DriveInfo]::new($root)).AvailableFreeSpace / 1GB)
        Write-Host "Free space on ${root}: $freeGB GB (about $($need[$root]) GB needed)"
        if ($freeGB -lt $need[$root]) {
            Fail "A new install needs about $($need[$root]) GB on $root (15 GB of Python environments in the home folder, 20 GB of models in their folder) and that drive has $freeGB GB free. Free some space, or choose other folders with -RaccontamiHome and -ModelsDir."
        }
    }
    Write-Host @"

This installs into $H, with the models in $Models,
and downloads about 35 GB: three Python environments (about 15 GB) and the models (about 20 GB).
On a fast connection that is around half an hour; on a slow one it can take hours. It can be
stopped and run again: what is already there is kept.
"@
}

New-Item -ItemType Directory -Force "$H\server-data", "$H\onnx", "$H\tts" | Out-Null
$env:PIP_CACHE_DIR = "$H\pip-cache"     # keeps the multi-GB downloads off C:
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:RACCONTAMI_HOME = $H
# the model download and the phone models do not read settings.txt: they are told the folder only when one
# was chosen, so that without one they follow a HF_HOME set on this computer, as the server does
if ($modelsChosen) { $env:RACCONTAMI_MODELS = $Models } else { Remove-Item Env:RACCONTAMI_MODELS -ErrorAction SilentlyContinue }

# the settings file is written before anything downloads, so a run stopped halfway and started again
# finds the models folder it chose
$start = "$H\start-server.bat"
if (-not (Test-Path $settings)) {
    # settings written into a start file made by an earlier version move here, so they are not lost
    $kept = @()
    if (Test-Path $start) {
        $kept = @(Get-Content $start | Where-Object { $_ -match '^\s*set\s+(RACCONTAMI_(?!HOME=)\w+=.+)$' } |
                  ForEach-Object { $Matches[1].Trim() })
    }
    @"
# Settings of the Raccontami server: one per line, NAME=value. Lines starting with # are notes.
# The installer only adds the models folder chosen when installing; it changes nothing else here.
# The README lists every setting.
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
if (-not $modelsFromEnv) { Add-ModelsSetting $settings $Models $usualModels }

# The port: 8765, unless settings.txt or the computer names another. On a new install, when another program
# holds 8765, the next free port is chosen and kept in settings.txt. A Python program on it may be the server.
function Get-PortListener($port) {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue; if ($p) { $p.ProcessName } else { "another program" } }
}
$Port = 0
if ($env:RACCONTAMI_PORT -match '^\d+$') { $Port = [int]$env:RACCONTAMI_PORT }
if (-not $Port -and (Test-Path $settings)) {
    $line = Get-Content -LiteralPath $settings -Encoding UTF8 | Where-Object { $_ -match '^\s*RACCONTAMI_PORT\s*=\s*"?(\d+)"?\s*$' } | Select-Object -Last 1
    if ($line -and $line -match '(\d+)') { $Port = [int]$Matches[1] }
}
$portNamed = [bool]$Port
if (-not $Port) { $Port = 8765 }
$holder = Get-PortListener $Port
if ($holder -and $holder -match '^python') {
    Fail "Port $Port is in use by $holder, probably the Raccontami server. Stop it first (its icon next to the clock, Stop the server), then run this again."
} elseif ($holder -and -not $portNamed -and $fresh) {
    $free = 8766..8799 | Where-Object { -not (Get-PortListener $_) } | Select-Object -First 1
    if (-not $free) { Fail "Ports 8765 to 8799 are all in use. Free one, or set RACCONTAMI_PORT in $settings, then run this again." }
    Write-Host "Port 8765 is used by $holder, so the server will use port $free. The app's Search local network looks on 8765: type the address the server's window shows."
    Add-Content -Encoding utf8 -LiteralPath $settings @("", "# The server's port: 8765 was taken by another program when installing. The phone's search looks on 8765, so type the address the server's window shows.", "RACCONTAMI_PORT=$free")
    $Port = $free
} elseif ($holder) {
    Write-Host "Port $Port, the server's port, is used by ${holder}: the server can start only when that program stops, or with another port (RACCONTAMI_PORT in $settings)."
}

function Ensure-Env($dir, $requirements, $label) {
    Step "Python environment: $label ($dir)"
    $python = "$dir\Scripts\python.exe"
    if (-not (Test-Path $python)) { & $py -m venv $dir; if ($LASTEXITCODE) { Fail "Could not create $dir" } }
    # in Windows PowerShell 5.1 a program's redirected error output stops the script under "Stop": a missing
    # torch writes a traceback there, which only means it is not installed yet
    try { & $python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() and torch.__version__.startswith('2.11') else 1)" 2>$null; $haveTorch = -not $LASTEXITCODE } catch { $haveTorch = $false }
    if (-not $haveTorch) {
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

if (-not $PhoneModels -or $SkipPhoneModels) {
    Write-Host "`nPhone models: not built here. The app downloads them from GitHub; -PhoneModels builds them here too."
} else {
    Step "Phone models (a second source for the app, which downloads them from GitHub first)"
    foreach ($m in "facebook/wav2vec2-base-960h", "jonatasgrosman/wav2vec2-large-xlsr-53-italian") {
        $name = $m.Split("/")[1]
        if (Test-Path "$H\onnx\$name.int8.onnx") { Write-Host "$name`: already there"; continue }
        & $serverPy "$Repo\tools\export_phone_model.py" $m "$H\onnx"
        if ($LASTEXITCODE) { Fail "Building the phone model $name failed." }
    }
}

Step "Settings and start script"
Write-Host $settings
Write-BatchFile $start @"
rem Starts the Raccontami server (port $Port). Made by install-windows.ps1, which writes it anew at
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
"@
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
$ruleName = "Raccontami $Port"
$ruleCommand = "New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Action Allow"
$ruleThere = [bool](Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)
if ($ruleThere) {
    Write-Host "Windows firewall: phones on your network can already reach the server"
} elseif (Ask "Let phones on your home network reach the server? Windows will ask for an administrator's permission.") {
    try {
        # the rule needs an administrator: only this one line is run as one
        Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "-NoProfile", "-Command", $ruleCommand
        $ruleThere = [bool](Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)
    } catch { $ruleThere = $false }
    Write-Host $(if ($ruleThere) { "Windows firewall: rule added (port $Port, from your own network only)" }
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
# the arrow as a character code: this script stays ASCII (Windows PowerShell reads it as ANSI)
if ($startedNow) { Write-Host "The server is starting in its own window. In the app: Settings $([char]0x2192) Server, Search local network.`n" }
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
