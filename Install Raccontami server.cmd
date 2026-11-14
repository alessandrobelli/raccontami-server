@echo off
rem Sets up the Raccontami server on this computer: save this one file and double-click it.
rem It needs nothing installed first. What it does is in install\setup.ps1, which it runs: from
rem beside this file when it is part of a copy of the code, otherwise straight from GitHub.
title Raccontami server setup
setlocal
if exist "%~dp0install\setup.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { & '%~dp0install\setup.ps1' } catch { exit 1 }"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol='Tls12'; iex ((New-Object Net.WebClient).DownloadString('https://raw.githubusercontent.com/alessandrobelli/raccontami-server/main/install/setup.ps1')) } catch { exit 1 }"
)
if errorlevel 1 (
    echo.
    echo The setup did not finish. The lines above say why. It can be run again: what is done is kept.
)
echo.
echo Press a key to close this window.
pause > nul
