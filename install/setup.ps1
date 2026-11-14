<#
.SYNOPSIS
  Sets up the Raccontami server on a Windows computer that has nothing installed for it yet.

  It brings what the installer needs and does not find: the server's code (as a zip, so git is not
  needed), a Python 3.12 of its own and ffmpeg. Everything goes into the home folder, nothing is
  added to the system, and no administrator is needed for this part. Then it runs the installer
  (install-windows.ps1), which makes the Python environments and downloads the models.

  Safe to run again: what is there is kept, and the server's code is brought up to date. That is
  also how to update.

.EXAMPLE
  In PowerShell, without downloading a file first:
    irm https://raw.githubusercontent.com/alessandrobelli/raccontami-server/main/install/setup.ps1 | iex

  Or double-click "Install Raccontami server.cmd", which does the same.
#>
param(
    [string]$RaccontamiHome,     # where everything goes; asked when not given
    [switch]$NoQuestions,        # ask nothing: the usual folder, and the installer's questions answered no
    [switch]$OnlyTools           # bring Python, ffmpeg and the code, and stop before the installer
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # the progress display of Windows PowerShell makes downloads many times slower
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$CodeZip = "https://github.com/alessandrobelli/raccontami-server/archive/refs/heads/main.zip"
$UvZip = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
$FfmpegZip = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

function Step($m) { Write-Host "`n== $m" -ForegroundColor Cyan }
$Stopped = "The setup did not finish. It can be run again: what is done is kept."
# not "exit": started with irm | iex this runs inside the reader's own PowerShell, which exit would close
function Fail($m) { Write-Host "`n$m" -ForegroundColor Red; throw $Stopped }

function Get-File($url, $to) {
    # curl comes with Windows 10 and 11, shows how far a download is, and is quick
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        & $curl.Source -L --fail --progress-bar -o $to $url
        if ($LASTEXITCODE) { Fail "Could not download $url. Check the internet connection and run this again." }
    } else {
        try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $to }
        catch { Fail "Could not download $url ($($_.Exception.Message)). Check the internet connection and run this again." }
    }
}

function Expand-To($zip, $folder) {
    if (Test-Path $folder) { Remove-Item -Recurse -Force $folder }
    Expand-Archive -Path $zip -DestinationPath $folder
}

Write-Host @"

Raccontami server: setup

This computer needs an NVIDIA graphics card with a driver of version 570 or newer.
The setup downloads about 35 GB in all and needs that much free space.
"@

# ---- where
$usual = Join-Path $env:USERPROFILE "raccontami"
if (-not $RaccontamiHome) {
    $RaccontamiHome = $usual
    if (-not $NoQuestions -and [Environment]::UserInteractive) {
        Write-Host "`nFree space:"
        Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -gt 0 } |
            ForEach-Object { Write-Host ("  {0}:  {1,5:N0} GB" -f $_.Name, ($_.Free / 1GB)) }
        $answer = (Read-Host "`nWhere should it go? Press Enter for $usual, or type a folder (for example D:\raccontami)").Trim().Trim('"')
        if ($answer) { $RaccontamiHome = $answer }
    }
}
$H = [System.IO.Path]::GetFullPath($RaccontamiHome)
$tools = Join-Path $H "tools"
$tmp = Join-Path $tools "download"

# ---- can this computer run it at all? Found out before anything is downloaded.
Step "Checking the computer"
try { $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null) } catch { $gpu = $null }
if (-not $gpu) { Fail "No NVIDIA graphics card was found (the program nvidia-smi, which comes with its driver, did not answer). The server needs one. If the computer has one, install its latest driver from nvidia.com and run this again." }
Write-Host "Graphics card: $(@($gpu)[0])"
$driver = 0
if (@($gpu)[0] -match ',\s*(\d+)\.[\d.]+\s*$') { $driver = [int]$Matches[1] }
if ($driver -and $driver -lt 570) { Fail "The NVIDIA driver is version $driver; the server needs 570 or newer. Update it from nvidia.com (or the NVIDIA app), then run this again." }
New-Item -ItemType Directory -Force $H | Out-Null
$freeGB = [math]::Floor(([System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($H))).AvailableFreeSpace / 1GB)
Write-Host "Home folder: $H   ($freeGB GB free on its drive)"
if (-not (Test-Path (Join-Path $H "env\Scripts\python.exe")) -and $freeGB -lt 35) {
    Fail "A new install needs about 35 GB and this drive has $freeGB GB free. Free some space, or run this again and choose a folder on another drive."
}
New-Item -ItemType Directory -Force $tools, $tmp | Out-Null

# ---- the server's code
Step "The server's code"
$here = if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { $null }
if ($here -and (Test-Path (Join-Path $here "raccontami_sync\serve.py"))) {
    $code = $here   # started from a copy of the code (a git clone): that copy is used as it is
    Write-Host "using the copy this setup was started from: $code"
} else {
    $code = Join-Path $H "raccontami-server"
    if (Test-Path (Join-Path $code ".git")) {
        Write-Host "$code is a git clone: left as it is (update it with git pull)"
    } else {
        if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
            Fail "A server seems to be running (port 8765 is in use). Stop it first: its icon next to the clock, Stop the server. Then run this again."
        }
        Get-File $CodeZip (Join-Path $tmp "code.zip")
        Expand-To (Join-Path $tmp "code.zip") (Join-Path $tmp "code")
        $fresh = Get-ChildItem (Join-Path $tmp "code") -Directory | Select-Object -First 1
        if (-not $fresh -or -not (Test-Path (Join-Path $fresh.FullName "raccontami_sync\serve.py"))) { Fail "The downloaded code is not what was expected. Run this again." }
        if (Test-Path $code) { Remove-Item -Recurse -Force $code }   # the code only: settings, token and jobs are elsewhere
        Move-Item $fresh.FullName $code
        Write-Host "code: $code"
    }
}

# ---- Python 3.12
Step "Python 3.12"
$python = $null
try { $python = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null) } catch { $python = $null }
if ($python -and (Test-Path $python)) {
    Write-Host "found on this computer: $python"
} else {
    $own = Join-Path $tools "python"
    $python = Get-ChildItem $own -Recurse -Filter python.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\(Scripts|venv)\\' } | Select-Object -First 1 -ExpandProperty FullName
    if ($python) {
        Write-Host "already there: $python"
    } else {
        # uv is one program that downloads a complete Python into a folder of our choice;
        # the environments and their packages are still made by Python's own venv and pip
        Write-Host "not on this computer: a Python of the server's own is downloaded into $own (about 45 MB)"
        Get-File $UvZip (Join-Path $tmp "uv.zip")
        Expand-To (Join-Path $tmp "uv.zip") (Join-Path $tools "uv")
        $uv = Get-ChildItem (Join-Path $tools "uv") -Recurse -Filter uv.exe | Select-Object -First 1 -ExpandProperty FullName
        if (-not $uv) { Fail "uv.exe was not in the download. Run this again." }
        $env:UV_PYTHON_INSTALL_DIR = $own
        $env:UV_CACHE_DIR = Join-Path $tools "uv-cache"
        # nothing outside the home folder: no entry among the installed Pythons, no program on the PATH
        & $uv python install 3.12 --no-registry --no-bin
        if ($LASTEXITCODE) { & $uv python install 3.12 }   # an uv without those two options
        if ($LASTEXITCODE) { Fail "Python could not be downloaded. Check the internet connection and run this again." }
        $python = Get-ChildItem $own -Recurse -Filter python.exe | Where-Object { $_.FullName -notmatch '\\(Scripts|venv)\\' } |
            Select-Object -First 1 -ExpandProperty FullName
        if (-not $python) { Fail "The downloaded Python was not found in $own." }
        Remove-Item -Recurse -Force $env:UV_CACHE_DIR -ErrorAction SilentlyContinue
        Write-Host "python: $python"
    }
}

# ---- ffmpeg
Step "ffmpeg"
$ffmpegBin = Join-Path $tools "ffmpeg\bin"
if (Test-Path (Join-Path $ffmpegBin "ffmpeg.exe")) {
    Write-Host "already there: $ffmpegBin"
} elseif (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "found on this computer: $((Get-Command ffmpeg).Source)"
} else {
    Write-Host "not on this computer: downloaded into $ffmpegBin (about 100 MB)"
    Get-File $FfmpegZip (Join-Path $tmp "ffmpeg.zip")
    Expand-To (Join-Path $tmp "ffmpeg.zip") (Join-Path $tmp "ffmpeg")
    $exe = Get-ChildItem (Join-Path $tmp "ffmpeg") -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    if (-not $exe) { Fail "ffmpeg.exe was not in the download. Run this again." }
    New-Item -ItemType Directory -Force $ffmpegBin | Out-Null
    Copy-Item $exe.FullName $ffmpegBin   # ffmpeg alone: the player and the prober beside it are not used, and are 200 MB
}
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

if ($OnlyTools) {
    Write-Host "`nPython, ffmpeg and the code are ready. The installer was not run (-OnlyTools)."
    return
}

# ---- the installer: environments, models, start files, firewall and login
$installer = Join-Path $code "install\install-windows.ps1"
& $installer -RaccontamiHome $H -Python $python -NoQuestions:$NoQuestions
# the installer says why it stopped; passed on, so that the window that started this says it did not finish
if ($LASTEXITCODE) { throw $Stopped }
