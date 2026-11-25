# Testing the Windows installer before a release

Do this before a new `Raccontami-Server-Setup.exe` replaces the one on the release `installer`.

Scanning the file is not enough. Defender's file scan finds nothing in an installer that its
behaviour monitoring later blocks while it runs: that happened to the old `.cmd`, flagged as
*Trojan:PowerShell/Sacepos.C*. So the test runs the installer on a clean Windows, the way a new user
would.

## Where

A clean Windows 11, not the developer's PC: earlier "Run anyway" choices, Defender exclusions and an
installed Python hide what a new user meets.

- **A virtual machine** (Hyper-V on Windows Pro, with Microsoft's Windows 11 evaluation image): the
  closest to a new user. Leave Defender as it comes, with cloud protection on. Smart App Control can
  only be on in a fresh install, so only a VM shows it.
- **Windows Sandbox** is quicker but resets on close. Check that Defender runs inside it:
  `Get-MpComputerStatus | Select RealTimeProtectionEnabled`.

Neither has an NVIDIA card, so open the installer from a terminal with `/SKIPGPUCHECK`. Add
`/DRYRUN` to stop before the Python packages and models (about 35 GB). Without `/DRYRUN` the whole
install runs, which needs the disk space and the time.

## Steps

1. Download the installer **with Edge**, from the build's artifact or the release, so it carries
   the internet mark (Mark of the Web) a real download has.
2. Open it: note whether *Windows protected your PC* appears, and whether Smart App Control blocks
   it. Write down exactly what Windows shows.
3. Go through the pages: folder, models folder, the two options. Tick the firewall option once and
   check that the permission prompt names *Network Command Shell* (netsh), from Microsoft.
4. Let it finish (with or without `/DRYRUN`) and start the server from the last page. In the second
   window (the Windows 95 style setup screen) check that the bar or the clock always moves, also
   during the long downloads, and that `setup-log.txt` in the server's folder holds the steps' output.
5. Open PowerShell and look for detections:

   ```powershell
   Get-MpThreatDetection | Format-List InitialDetectionTime, ThreatID, Resources
   Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Windows Defender/Operational'; Id=1116,1117,1121,1122} -MaxEvents 20 |
     Format-List TimeCreated, Id, Message
   ```

   Events 1116/1117 are detections and 1121/1122 are blocks by attack-surface-reduction rules. Each
   one shows the threat's name, the process and the command line.
6. Run the installer again over the same folder (an update): no models question, nothing
   downloaded again.
7. Uninstall from **Settings → Apps**: answer the questions about the models and the data, then check
   that the folder holds only what you chose to keep.

## When Defender flags it

- Note the threat name and the command line from the event.
- Submit the file as a developer false positive: <https://www.microsoft.com/wdsi/filesubmission>.
- Do not publish that build. Change what the installer does, rather than how it looks: hiding
  behaviour is what malware does, and it is not a fix.

## Building

`installer\build.ps1 -Iscc <path to ISCC.exe>` builds it locally (Inno Setup 6.7.4). The *Windows
installer* workflow on GitHub builds the same file on a clean Windows machine, scans it with
Defender's file scanner, and keeps it with its SHA-256 as a download of the run.
