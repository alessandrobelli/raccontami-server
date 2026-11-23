<#
.SYNOPSIS
  Builds the Windows installer, installer\output\Raccontami-Server-Setup.exe. Runs on the developer's PC or
  on GitHub (.github\workflows\installer.yml), never on users' PCs.

  It downloads the Python that goes inside the installer (python.org's NuGet package and its Tcl/Tk part,
  pinned and checked by SHA-256), puts them together in installer\build\python, and compiles
  installer\raccontami.iss with Inno Setup.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File installer\build.ps1 -Iscc F:\tools\innosetup\ISCC.exe
#>
param(
    [string]$Iscc = "ISCC.exe"   # Inno Setup 6.7's command-line compiler
)
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$Repo = Split-Path -Parent $Here

# Pinned downloads: change the version and its hash together
$PythonVersion = "3.12.10"
$Pieces = @(
    @{ Name = "python.zip"; Sha256 = "0eb85c2dfccccf1b17352de4c397f69194035b7d37149eacc16f1147d93de3b8"
       Url = "https://api.nuget.org/v3-flatcontainer/python/$PythonVersion/python.$PythonVersion.nupkg" },
    @{ Name = "tcltk.msi"; Sha256 = "55c96ffad69b1c834aa52e11b9ce41637a178ba6ad6607e83956044834276e2a"
       Url = "https://www.python.org/ftp/python/$PythonVersion/amd64/tcltk.msi" }
)

$cache = Join-Path $Here "cache"
$build = Join-Path $Here "build"
New-Item -ItemType Directory -Force $cache | Out-Null
foreach ($p in $Pieces) {
    $file = Join-Path $cache $p.Name
    if (-not (Test-Path $file) -or (Get-FileHash $file).Hash -ne $p.Sha256.ToUpper()) {
        Write-Host "downloading $($p.Url)"
        & curl.exe -sSL --fail -o $file $p.Url
        if ($LASTEXITCODE) { throw "Download failed: $($p.Url)" }
    }
    $hash = (Get-FileHash $file).Hash
    if ($hash -ne $p.Sha256.ToUpper()) { throw "$($p.Name) has SHA-256 $hash, expected $($p.Sha256)" }
}

# Python: the NuGet package's "tools" folder is a complete Python; tkinter (the Connect window) comes from
# tcltk.msi, unpacked without installing (an administrative install only copies its files out)
if (Test-Path $build) { Remove-Item -Recurse -Force $build }
$unpacked = Join-Path $build "unpacked"
$python = Join-Path $build "python"
Expand-Archive -Path (Join-Path $cache "python.zip") -DestinationPath (Join-Path $unpacked "nuget")
Move-Item (Join-Path $unpacked "nuget\tools") $python
$msi = Start-Process msiexec.exe -ArgumentList "/a", "`"$(Join-Path $cache 'tcltk.msi')`"", "/qn", "TARGETDIR=`"$(Join-Path $unpacked 'tcltk')`"" -Wait -PassThru
if ($msi.ExitCode) { throw "Unpacking tcltk.msi failed ($($msi.ExitCode))" }
foreach ($sub in "DLLs", "Lib\tkinter", "tcl") {
    New-Item -ItemType Directory -Force (Join-Path $python $sub) | Out-Null
    Copy-Item -Path (Join-Path $unpacked "tcltk\$sub\*") -Destination (Join-Path $python $sub) -Recurse -Force
}
# not used by the server, and the only unsigned files in Tcl/Tk
Remove-Item -Recurse -Force (Join-Path $python "tcl\nmake"), (Join-Path $python "tcl\tix8.4.3")
Remove-Item -Recurse -Force $unpacked
& (Join-Path $python "python.exe") -c "import tkinter, venv, ensurepip, ssl, sqlite3"
if ($LASTEXITCODE) { throw "The assembled Python is missing a module" }

$version = (Get-Content (Join-Path $Repo "version.json") -Raw | ConvertFrom-Json).version
Write-Host "compiling the installer for version $version"
& $Iscc "/DAppVersion=$version" "/DRepo=$Repo" "/DPythonDir=$python" (Join-Path $Here "raccontami.iss")
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Get-Item (Join-Path $Here "output\Raccontami-Server-Setup.exe") | ForEach-Object { "{0}  {1:N1} MB" -f $_.FullName, ($_.Length / 1MB) }
