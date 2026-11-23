; The Raccontami server's Windows installer. Built by installer\build.ps1, which passes:
;   AppVersion  from version.json
;   Repo        the repository folder (the server's code is taken from there)
;   PythonDir   the Python assembled for the installer (python.org's NuGet package + Tcl/Tk)
;
; What it does, in order: checks the NVIDIA driver, asks for the home folder and (on a new install) the
; models folder, checks the free space, copies the code and Python, downloads ffmpeg (pinned, SHA-256),
; then runs install\install.py in a window of its own for the environments and the models (about 35 GB).
; It installs for the current user only; only the firewall rule asks for an administrator, through netsh.
;
; For scripted installs: /MODELSDIR=<folder> chooses the models folder on a new install. A silent uninstall keeps
; the models and the server's data unless given /DELETEMODELS or /DELETEDATA.
; Switches for testing only: /SKIPGPUCHECK (a PC or VM without an NVIDIA card) and /DRYRUN (install.py only
; says what it would do: no Python packages or models; ffmpeg, 34 MB, still downloads).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Repo
  #define Repo ".."
#endif
#ifndef PythonDir
  #define PythonDir "build\python"
#endif

#define FfmpegUrl "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.7z"
#define FfmpegSha256 "4705843ccaaf54257c16ad90f3e952ece33c17df964ecf7bfdbb0f49c7171077"
#define FfmpegFolder "ffmpeg-9.0.2-essentials_build"
#define RuleName "Raccontami 8765"

[Setup]
AppId={{7791F22F-AA41-462E-8A3A-2EEC6F757AB3}
AppName=Raccontami server
AppVersion={#AppVersion}
AppVerName=Raccontami server {#AppVersion}
AppPublisher=Raccontami
AppPublisherURL=https://github.com/alessandrobelli/raccontami-server
AppSupportURL=https://github.com/alessandrobelli/raccontami-server#troubleshooting
DefaultDirName={%USERPROFILE}\raccontami
DefaultGroupName=Raccontami server
DisableProgramGroupPage=yes
DirExistsWarning=no
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ArchiveExtraction=enhanced/nopassword
CloseApplications=no
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
SetupLogging=yes
UninstallDisplayName=Raccontami server
OutputDir=output
OutputBaseFilename=Raccontami-Server-Setup

[Messages]
SelectDirLabel3=Setup will put the Raccontami server in the following folder: its code, its own Python and ffmpeg, and its Python packages (about 15 GB).
SelectDirBrowseLabel=To continue, click Next. Nothing is installed in Windows itself.

[Tasks]
Name: "firewall"; Description: "Let phones on my home network reach the server (Windows asks for permission once)"
Name: "startatlogin"; Description: "Start the server when I log in to Windows (without a window, as an icon next to the clock)"; Flags: unchecked

[Files]
; The server's code. A code folder that is a git clone is left alone (update it with git pull).
Source: "{#Repo}\raccontami_sync\*"; Excludes: "*.pyc,__pycache__"; DestDir: "{app}\raccontami-server\raccontami_sync"; Flags: ignoreversion recursesubdirs; Check: CodeCanBeReplaced
Source: "{#Repo}\install\*"; Excludes: "*.pyc,__pycache__"; DestDir: "{app}\raccontami-server\install"; Flags: ignoreversion recursesubdirs; Check: CodeCanBeReplaced
Source: "{#Repo}\tools\*"; Excludes: "*.pyc,__pycache__"; DestDir: "{app}\raccontami-server\tools"; Flags: ignoreversion recursesubdirs; Check: CodeCanBeReplaced
Source: "{#Repo}\voices\*"; DestDir: "{app}\raccontami-server\voices"; Flags: ignoreversion recursesubdirs skipifsourcedoesntexist; Check: CodeCanBeReplaced
Source: "{#Repo}\requirements*.txt"; DestDir: "{app}\raccontami-server"; Flags: ignoreversion; Check: CodeCanBeReplaced
Source: "{#Repo}\version.json"; DestDir: "{app}\raccontami-server"; Flags: ignoreversion; Check: CodeCanBeReplaced
Source: "{#Repo}\LICENSE"; DestDir: "{app}\raccontami-server"; Flags: ignoreversion; Check: CodeCanBeReplaced
Source: "{#Repo}\README.md"; DestDir: "{app}\raccontami-server"; Flags: ignoreversion; Check: CodeCanBeReplaced
; Python, only when this home folder has none yet: the environments belong to the Python that made them
Source: "{#PythonDir}\*"; DestDir: "{app}\tools\python"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: NeedPython
; ffmpeg (GPL, so downloaded rather than shipped): only ffmpeg.exe is kept, see CurStepChanged
Source: "{#FfmpegUrl}"; DestName: "ffmpeg.7z"; DestDir: "{tmp}\ffmpeg"; ExternalSize: 35442000; Hash: "{#FfmpegSha256}"; \
  Flags: external download extractarchive recursesubdirs ignoreversion deleteafterinstall; Check: NeedFfmpeg

[Icons]
Name: "{app}\Raccontami server (no window)"; Filename: "{app}\env\Scripts\pythonw.exe"; Parameters: "-m raccontami_sync.background --home ""{app}"""; WorkingDir: "{app}\raccontami-server"; Comment: "Starts the Raccontami server without a window; its icon next to the clock stops it"
Name: "{group}\Raccontami server"; Filename: "{app}\env\Scripts\pythonw.exe"; Parameters: "-m raccontami_sync.background --home ""{app}"""; WorkingDir: "{app}\raccontami-server"; Comment: "Starts the Raccontami server without a window; its icon next to the clock stops it"
Name: "{group}\Raccontami server (with a window)"; Filename: "{app}\start-server.bat"; WorkingDir: "{app}"; Comment: "Starts the Raccontami server in a window that shows how to connect the phone"
Name: "{group}\Raccontami server folder"; Filename: "{app}"
Name: "{group}\Uninstall Raccontami server"; Filename: "{uninstallexe}"
Name: "{userstartup}\Raccontami server"; Filename: "{app}\env\Scripts\pythonw.exe"; Parameters: "-m raccontami_sync.background --home ""{app}"""; WorkingDir: "{app}\raccontami-server"; Tasks: startatlogin

[Run]
Filename: "{app}\start-server.bat"; Description: "Start the server now (its window shows how to connect the phone)"; Flags: postinstall nowait shellexec skipifsilent; Check: InstallSucceeded

[Code]
var
  ModelsPage: TInputDirWizardPage;
  ModelsPageDefault: String;
  StepsSucceeded: Boolean;
  PythonCheckedFor: String;
  PythonNeeded: Boolean;

function Switch(const Name: String): Boolean;
begin
  Result := Pos('/' + Uppercase(Name), Uppercase(GetCmdTail)) > 0;
end;

function IsNewInstall: Boolean;
begin
  Result := not FileExists(ExpandConstant('{app}\env\Scripts\python.exe'));
end;

function CodeCanBeReplaced: Boolean;
begin
  Result := not DirExists(ExpandConstant('{app}\raccontami-server\.git'));
end;

{ Decided once per folder: Inno Setup asks before every file, and after the first one Python "exists" }
function NeedPython: Boolean;
begin
  if PythonCheckedFor <> ExpandConstant('{app}') then
  begin
    PythonCheckedFor := ExpandConstant('{app}');
    PythonNeeded := not FileExists(PythonCheckedFor + '\tools\python\python.exe');
  end;
  Result := PythonNeeded;
end;

function NeedFfmpeg: Boolean;
begin
  Result := not FileExists(ExpandConstant('{app}\tools\ffmpeg\bin\ffmpeg.exe'));
end;

function InstallSucceeded: Boolean;
begin
  Result := StepsSucceeded and not Switch('DRYRUN');
end;

{ A folder for a command line: "D:\x\" would lose its closing quote to the backslash, so the last backslash
  goes, and a drive's root becomes "E:\." }
function QuoteFolder(const Folder: String): String;
var
  F: String;
begin
  F := RemoveBackslashUnlessRoot(Folder);
  if (Length(F) > 0) and (F[Length(F)] = '\') then
    F := F + '.';
  Result := '"' + F + '"';
end;

{ The I-th field of a line of fields separated by spaces, or '' }
function Field(Line: String; I: Integer): String;
var
  P: Integer;
begin
  Line := Trim(Line);
  while I > 0 do
  begin
    P := Pos(' ', Line);
    if P = 0 then
    begin
      Line := '';
      Break;
    end;
    Line := Trim(Copy(Line, P + 1, MaxInt));
    I := I - 1;
  end;
  P := Pos(' ', Line);
  if P > 0 then
    Result := Copy(Line, 1, P - 1)
  else
    Result := Line;
end;

{ A program listening on port 8765. netstat's state column is translated on other Windows languages, so a
  listening row is recognised by its shape: local address ending in :8765, no foreign address (0.0.0.0:0, [::]:0) }
function ServerRunning: Boolean;
var
  Code, I: Integer;
  Output: TExecOutput;
  Local, Foreign: String;
begin
  Result := False;
  if ExecAndCaptureOutput(ExpandConstant('{sys}\netstat.exe'), '-ano -p TCP', '', SW_SHOWNORMAL, ewWaitUntilTerminated, Code, Output) then
    for I := 0 to GetArrayLength(Output.StdOut) - 1 do
    begin
      Local := Field(Output.StdOut[I], 1);
      Foreign := Field(Output.StdOut[I], 2);
      if (Copy(Local, Length(Local) - 4, 5) = ':8765') and ((Foreign = '0.0.0.0:0') or (Foreign = '[::]:0')) then
        Result := True;
    end;
  if ExecAndCaptureOutput(ExpandConstant('{sys}\netstat.exe'), '-ano -p TCPv6', '', SW_SHOWNORMAL, ewWaitUntilTerminated, Code, Output) then
    for I := 0 to GetArrayLength(Output.StdOut) - 1 do
    begin
      Local := Field(Output.StdOut[I], 1);
      Foreign := Field(Output.StdOut[I], 2);
      if (Copy(Local, Length(Local) - 4, 5) = ':8765') and ((Foreign = '0.0.0.0:0') or (Foreign = '[::]:0')) then
        Result := True;
    end;
  Log('server running on 8765: ' + IntToStr(Ord(Result)));
end;

function FirewallRuleExists: Boolean;
var
  Code: Integer;
  Output: TExecOutput;
begin
  Result := ExecAndCaptureOutput(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall show rule name="{#RuleName}"', '',
    SW_SHOWNORMAL, ewWaitUntilTerminated, Code, Output) and (Code = 0);
end;

{ The NVIDIA driver: the voices need CUDA 12.8, which drivers before 570 do not have }
function InitializeSetup: Boolean;
var
  Code, Major, Comma: Integer;
  Output: TExecOutput;
  Line, Smi: String;
begin
  Result := True;
  if Switch('SKIPGPUCHECK') then
    Exit;
  // the driver puts nvidia-smi in the 64-bit System32 (the sys constant in 64-bit install mode); a bare name is the fallback
  Smi := ExpandConstant('{sys}\nvidia-smi.exe');
  if not FileExists(Smi) then
    Smi := 'nvidia-smi.exe';
  Log('nvidia-smi: ' + Smi);
  if not ExecAndCaptureOutput(Smi, '--query-gpu=name,driver_version --format=csv,noheader', '',
       SW_SHOWNORMAL, ewWaitUntilTerminated, Code, Output) or (Code <> 0) or (GetArrayLength(Output.StdOut) = 0) then
  begin
    SuppressibleMsgBox('No NVIDIA graphics card was found (the program nvidia-smi, which comes with its driver, did not answer). ' +
      'The server needs one. If this computer has one, install its latest driver from nvidia.com and open this installer again.',
      mbCriticalError, MB_OK, IDOK);
    Result := False;
    Exit;
  end;
  Line := Trim(Output.StdOut[0]);
  Comma := Pos(',', Line);
  Major := StrToIntDef(Copy(Trim(Copy(Line, Comma + 1, MaxInt)), 1, Pos('.', Trim(Copy(Line, Comma + 1, MaxInt))) - 1), 0);
  Log('graphics card: ' + Line + '; driver major version ' + IntToStr(Major));
  if (Major > 0) and (Major < 570) then
  begin
    SuppressibleMsgBox('The NVIDIA driver is version ' + IntToStr(Major) + '; the server needs 570 or newer. ' +
      'Update it from nvidia.com (or the NVIDIA app), then open this installer again.', mbCriticalError, MB_OK, IDOK);
    Result := False;
  end;
end;

procedure InitializeWizard;
var
  Note: String;
begin
  Note := 'The models take about 20 GB and can go on another drive. Click Next to keep them in the server''s folder, or choose another folder.';
  if GetEnv('HF_HOME') <> '' then
    Note := Note + #13#10#13#10 + 'HF_HOME is set on this computer: with the usual folder, the Hugging Face models (nearly all of them) go to ' +
      GetEnv('HF_HOME') + '; with another folder, all the models go there.';
  ModelsPage := CreateInputDirPage(wpSelectDir, 'Where should the models go?', 'The speech and voice models the server downloads',
    Note, False, '');
  ModelsPage.Add('');
  ModelsPage.Values[0] := ExpandConstant('{param:MODELSDIR|}');  { a scripted install: /MODELSDIR=E:\models }
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { the models folder is asked once, on a new install; later runs use the one in settings.txt }
  Result := (PageID = ModelsPage.ID) and ((not IsNewInstall) or (GetEnv('RACCONTAMI_MODELS') <> ''));
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = ModelsPage.ID then
    if (ModelsPage.Values[0] = '') or (ModelsPage.Values[0] = ModelsPageDefault) then
    begin
      ModelsPageDefault := AddBackslash(WizardDirValue) + 'models';
      ModelsPage.Values[0] := ModelsPageDefault;
    end;
end;

function GB(const Drive: String): Integer;
var
  Free, Total: Int64;
begin
  Result := MaxInt;
  if GetSpaceOnDisk64(AddBackslash(Drive), Free, Total) then
    Result := Free div (1024 * 1024 * 1024);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  HomeDrive, ModelsDrive: String;
begin
  Result := True;
  if (CurPageID = ModelsPage.ID) and IsNewInstall then
  begin
    HomeDrive := ExtractFileDrive(WizardDirValue);
    ModelsDrive := ExtractFileDrive(ModelsPage.Values[0]);
    { with the usual folder, a HF_HOME set on the computer keeps nearly all of the models }
    if (CompareText(RemoveBackslash(ModelsPage.Values[0]), RemoveBackslash(ModelsPageDefault)) = 0) and (GetEnv('HF_HOME') <> '') then
      ModelsDrive := ExtractFileDrive(GetEnv('HF_HOME'));
    if CompareText(HomeDrive, ModelsDrive) = 0 then
    begin
      if GB(HomeDrive) < 35 then
      begin
        MsgBox('A new install needs about 35 GB on ' + HomeDrive + ' (15 GB of Python packages, 20 GB of models) and it has ' +
          IntToStr(GB(HomeDrive)) + ' GB free. Free some space, or choose folders on another drive.', mbError, MB_OK);
        Result := False;
      end;
    end else if GB(HomeDrive) < 15 then
    begin
      MsgBox('The Python packages need about 15 GB on ' + HomeDrive + ' and it has ' + IntToStr(GB(HomeDrive)) +
        ' GB free. Free some space, or choose another folder for the server.', mbError, MB_OK);
      Result := False;
    end else if GB(ModelsDrive) < 20 then
    begin
      MsgBox('The models need about 20 GB on ' + ModelsDrive + ' and it has ' + IntToStr(GB(ModelsDrive)) +
        ' GB free. Free some space, or choose another folder for the models.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if ServerRunning then
    Result := 'A server seems to be running (port 8765 is in use). Stop it first: its icon next to the clock, Stop the server. ' +
      'Then click Back and Next, or open this installer again.';
end;

procedure CopyFfmpeg;
var
  Bin: String;
begin
  Bin := ExpandConstant('{app}\tools\ffmpeg\bin');
  if FileExists(ExpandConstant('{tmp}\ffmpeg\{#FfmpegFolder}\bin\ffmpeg.exe')) then
  begin
    ForceDirectories(Bin);
    if not CopyFile(ExpandConstant('{tmp}\ffmpeg\{#FfmpegFolder}\bin\ffmpeg.exe'), Bin + '\ffmpeg.exe', False) then
      SuppressibleMsgBox('ffmpeg could not be copied to ' + Bin + '.', mbError, MB_OK, IDOK);
  end;
end;

procedure RunSteps;
var
  Params, Models: String;
  Code: Integer;
begin
  Params := '-u ' + AddQuotes(ExpandConstant('{app}\raccontami-server\install\install.py')) +
    ' --home ' + QuoteFolder(ExpandConstant('{app}')) + ' --pause-on-error';
  Models := ModelsPage.Values[0];
  if IsNewInstall and (GetEnv('RACCONTAMI_MODELS') = '') and (Models <> '') then
    Params := Params + ' --models ' + QuoteFolder(Models);
  if Switch('DRYRUN') then
    Params := Params + ' --dry-run';
  WizardForm.StatusLabel.Caption := 'Installing the Python packages and the models in the other window (about 35 GB the first time)...';
  Log('install.py ' + Params);
  StepsSucceeded := Exec(ExpandConstant('{app}\tools\python\python.exe'), Params, ExpandConstant('{app}'),
    SW_SHOWNORMAL, ewWaitUntilTerminated, Code) and (Code = 0);
  if not StepsSucceeded then
    SuppressibleMsgBox('The installation did not finish: the other window said why. Open this installer again to continue; ' +
      'what is done is kept.', mbError, MB_OK, IDOK);
end;

procedure AddFirewallRule;
var
  Code: Integer;
begin
  if FirewallRuleExists then
    Exit;
  WizardForm.StatusLabel.Caption := 'Adding the firewall rule (Windows asks for permission)...';
  ShellExec('runas', ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall add rule name="{#RuleName}" dir=in action=allow protocol=TCP localport=8765 remoteip=localsubnet',
    '', SW_HIDE, ewWaitUntilTerminated, Code);
  if not FirewallRuleExists then
    SuppressibleMsgBox('The firewall rule was not added, so phones cannot reach the server yet. Open this installer again and allow it, ' +
      'or see the README (Troubleshooting).', mbInformation, MB_OK, IDOK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    CopyFfmpeg;
    { before the long step: the user is still there to answer Windows' permission prompt }
    if WizardIsTaskSelected('firewall') then
      AddFirewallRule;
    RunSteps;
  end;
end;

{ ---- Uninstall: only what the installer made, by name. The models and the server's data are asked about. }

function InitializeUninstall: Boolean;
begin
  Result := True;
  if ServerRunning then
  begin
    SuppressibleMsgBox('A server seems to be running (port 8765 is in use). Stop it first: its icon next to the clock, Stop the server. ' +
      'Then uninstall again.', mbError, MB_OK, IDOK);
    Result := False;
  end;
end;

{ The models folder settings.txt names, read as the server reads it (raccontami_sync/settings.py), or '' }
function ModelsFolderNamed(const Home: String): String;
var
  Lines: TArrayOfString;
  I, Eq: Integer;
  L, Value: String;
begin
  Result := '';
  if LoadStringsFromFile(Home + '\settings.txt', Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
    begin
      L := Trim(Lines[I]);
      Eq := Pos('=', L);
      if (Eq > 0) and (Copy(L, 1, 1) <> '#') and (CompareText(Trim(Copy(L, 1, Eq - 1)), 'RACCONTAMI_MODELS') = 0) then
      begin
        Value := RemoveQuotes(Trim(Copy(L, Eq + 1, MaxInt)));
        if Value <> '' then
          Result := Value;
      end;
    end;
end;

{ The models folder may be any folder the user named, even a drive's root: only the subfolders the server
  makes there are deleted, then the folder itself if that left it empty }
procedure DeleteModels(const Models: String);
begin
  DelTree(AddBackslash(Models) + 'hf', True, True, True);
  DelTree(AddBackslash(Models) + 'whisper', True, True, True);
  DelTree(AddBackslash(Models) + 'torch', True, True, True);
  RemoveDir(Models);
end;

procedure DeleteMade(const Path: String);
begin
  if DirExists(Path) then
    DelTree(Path, True, True, True)
  else if FileExists(Path) then
    DeleteFile(Path);
end;

{ Asked in a normal uninstall; a silent one (scripts) answers no, unless the switch says yes:
  /DELETEMODELS, /DELETEDATA }
function Answer(const Question, YesSwitch: String): Boolean;
begin
  if UninstallSilent then
    Result := Switch(YesSwitch)
  else
    Result := MsgBox(Question, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  Log(YesSwitch + ': ' + IntToStr(Ord(Result)));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Home, Models: String;
  Code: Integer;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  Home := ExpandConstant('{app}');
  if FirewallRuleExists then
    if SuppressibleMsgBox('Remove the firewall rule "{#RuleName}"? Windows asks for permission.', mbConfirmation, MB_YESNO, IDNO) = IDYES then
      ShellExec('runas', ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="{#RuleName}"', '', SW_HIDE,
        ewWaitUntilTerminated, Code);
  DeleteMade(Home + '\env');
  DeleteMade(Home + '\tts\env-a');
  DeleteMade(Home + '\tts\env-c');
  DeleteMade(Home + '\tts\cache');
  DeleteMade(Home + '\tools\python');
  DeleteMade(Home + '\tools\ffmpeg');
  DeleteMade(Home + '\pip-cache');
  DeleteMade(Home + '\start-server.bat');
  if not DirExists(Home + '\raccontami-server\.git') then
    DeleteMade(Home + '\raccontami-server');
  Models := ModelsFolderNamed(Home);
  if Models = '' then
    Models := Home + '\models';
  if DirExists(AddBackslash(Models) + 'hf') or DirExists(AddBackslash(Models) + 'whisper') or DirExists(AddBackslash(Models) + 'torch') then
    if Answer('Also delete the downloaded models in ' + Models + ' (about 20 GB)? They download again if you install the server later.',
         'DELETEMODELS') then
      DeleteModels(Models);
  if DirExists(Home + '\server-data') then
    if Answer('Also delete the server''s data in ' + Home + ' (finished jobs, the token, the certificate the phone trusts, settings.txt)? ' +
         'Keep it to reinstall later without connecting the phone again.', 'DELETEDATA') then
    begin
      DeleteMade(Home + '\server-data');
      DeleteMade(Home + '\onnx');
      DeleteMade(Home + '\settings.txt');
    end;
  RemoveDir(Home + '\tts');
  RemoveDir(Home + '\tools');
end;

procedure DeinitializeUninstall;
begin
  RemoveDir(ExpandConstant('{app}'));
end;
