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
; The port is 8765, or the next free one when another program holds 8765 (kept in settings.txt).
; For scripted installs: /MODELSDIR=<folder> chooses the models folder on a new install, /PORT=<n> the port,
; /LANGUAGES=en,es the languages (raccontami_sync\languages.py lists them). A silent uninstall keeps
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

; /DTestBuild: an installer for tests, registered apart from a real install on the same PC (its own entry in
; Windows' installed apps and its own Start menu group), so a test never replaces or removes the real one
#ifdef TestBuild
  #define AppIdGuid "{{B0C6E2A4-5D1F-4E8B-9A3C-7F2D1E6B4A90}"
  #define AppTitle "Raccontami server (test build)"
#else
  #define AppIdGuid "{{7791F22F-AA41-462E-8A3A-2EEC6F757AB3}"
  #define AppTitle "Raccontami server"
#endif

[Setup]
AppId={#AppIdGuid}
AppName={#AppTitle}
AppVersion={#AppVersion}
AppVerName={#AppTitle} {#AppVersion}
AppPublisher=Raccontami
AppPublisherURL=https://github.com/alessandrobelli/raccontami-server
AppSupportURL=https://github.com/alessandrobelli/raccontami-server#troubleshooting
DefaultDirName={%USERPROFILE}\raccontami
DefaultGroupName={#AppTitle}
DisableProgramGroupPage=yes
DirExistsWarning=no
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ArchiveExtraction=enhanced/nopassword
CloseApplications=no
WizardStyle=modern
; Inno Setup 6.6 dropped resizable wizards: the largest size instead, for the language list and its models
WizardSizePercent=150,150
Compression=lzma2/max
SolidCompression=yes
SetupLogging=yes
UninstallDisplayName={#AppTitle}
OutputDir=output
OutputBaseFilename=Raccontami-Server-Setup

[Messages]
SelectDirLabel3=Setup will put the Raccontami server in the following folder: its code, its own Python and ffmpeg, and its Python packages (about 15 GB).
SelectDirBrowseLabel=To continue, click Next. Nothing is installed in Windows itself.

[Tasks]
Name: "firewall"; Description: "Let phones on my home network reach the server (adds one Windows firewall rule; Windows asks permission for its firewall tool, ""Network Command Shell"")"
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
  ServerPort: Integer;     { the port the server will use }
  PortChosenNow: Boolean;  { chosen by this run (8765 was taken, or /PORT=): passed to install.py, kept in settings.txt }
  { the languages, from raccontami_sync\languages.py (build\languages.iss, made by installer\languages_iss.py) }
  LangCode, LangName, LangVoice: TArrayOfString;
  LangWindows: TArrayOfInteger;
  LangTested, LangMade: array of Boolean;
  LangAligner, VoiceLabel: TArrayOfString;
  DefaultNarrator: String;
  VoiceName: TArrayOfString;
  VoiceModel10, VoiceEnv10: TArrayOfInteger;  { GB, in tenths }
  Aligner10: Integer;
  LangPage: TInputOptionWizardPage;
  LangDetails: TNewMemo;
  NarratorPage: TInputQueryWizardPage;
  RemakeBox: TNewCheckBox;
  { graphics cards: their text, nvidia-smi index (-1: not NVIDIA), whether suitable }
  GpuText: TArrayOfString;
  GpuIndex: TArrayOfInteger;
  GpuOk: array of Boolean;
  NvidiaCount, SuitableCount: Integer;
  RemoveUnticked: Boolean;  { the files of the languages unticked on an update are deleted (the user said yes) }
  GpuPage: TInputOptionWizardPage;
  LangPageFilled: Boolean;

#include "build\languages.iss"

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

{ The last field of a line of fields separated by spaces }
function LastField(Line: String): String;
var
  P: Integer;
begin
  Line := Trim(Line);
  P := Pos(' ', Line);
  while P > 0 do
  begin
    Line := Trim(Copy(Line, P + 1, MaxInt));
    P := Pos(' ', Line);
  end;
  Result := Line;
end;

{ The process listening on a port, or 0. netstat's state column is translated on other Windows languages
  (sometimes into two words), so a listening row is recognised by its shape: local address ending in :<port>,
  no foreign address (0.0.0.0:0 or [::]:0); the process number is the row's last field }
function ListenerPid(Port: Integer): Integer;
var
  Code, I, P: Integer;
  Output: TExecOutput;
  Local, Foreign, Proto, Tail: String;
begin
  Result := 0;
  Tail := ':' + IntToStr(Port);
  for P := 0 to 1 do
  begin
    if P = 0 then Proto := 'TCP' else Proto := 'TCPv6';
    if ExecAndCaptureOutput(ExpandConstant('{sys}\netstat.exe'), '-ano -p ' + Proto, '', SW_SHOWNORMAL, ewWaitUntilTerminated, Code, Output) then
      for I := 0 to GetArrayLength(Output.StdOut) - 1 do
      begin
        Local := Field(Output.StdOut[I], 1);
        Foreign := Field(Output.StdOut[I], 2);
        if (Copy(Local, Length(Local) - Length(Tail) + 1, Length(Tail)) = Tail) and ((Foreign = '0.0.0.0:0') or (Foreign = '[::]:0')) then
          Result := StrToIntDef(LastField(Output.StdOut[I]), -1);
      end;
  end;
  Log('listening on ' + IntToStr(Port) + ': process ' + IntToStr(Result));
end;

{ The program name of a process ("python.exe"), or '' }
function ProgramName(Pid: Integer): String;
var
  Code: Integer;
  Output: TExecOutput;
begin
  Result := '';
  if (Pid > 0) and ExecAndCaptureOutput(ExpandConstant('{sys}\tasklist.exe'), '/FI "PID eq ' + IntToStr(Pid) + '" /FO CSV /NH', '',
       SW_SHOWNORMAL, ewWaitUntilTerminated, Code, Output) and (GetArrayLength(Output.StdOut) > 0) and (Copy(Output.StdOut[0], 1, 1) = '"') then
    Result := Copy(Output.StdOut[0], 2, Pos('","', Output.StdOut[0]) - 2);
end;

function RuleName(Port: Integer): String;
begin
  Result := 'Raccontami ' + IntToStr(Port);
end;

function FirewallRuleExists(Port: Integer): Boolean;
var
  Code: Integer;
  Output: TExecOutput;
begin
  Result := ExecAndCaptureOutput(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall show rule name="' + RuleName(Port) + '"', '',
    SW_SHOWNORMAL, ewWaitUntilTerminated, Code, Output) and (Code = 0);
end;

{ A setting in settings.txt, read as the server reads it (raccontami_sync/settings.py), or '' }
function SettingNamed(const Home, Name: String): String;
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
      if (Eq > 0) and (Copy(L, 1, 1) <> '#') and (CompareText(Trim(Copy(L, 1, Eq - 1)), Name) = 0) then
      begin
        Value := RemoveQuotes(Trim(Copy(L, Eq + 1, MaxInt)));
        if Value <> '' then
          Result := Value;
      end;
    end;
end;

{ The port the server uses, in its own order: set on the computer, then settings.txt; 0 when neither names one }
function PortNamed(const Home: String): Integer;
begin
  Result := StrToIntDef(GetEnv('RACCONTAMI_PORT'), 0);
  if Result <= 0 then
    Result := StrToIntDef(SettingNamed(Home, 'RACCONTAMI_PORT'), 0);
end;
{ ---- Graphics cards. The server needs an NVIDIA card with 8 GB and a driver of version 570 or newer (CUDA 12.8).
  The cards are found here; a page shows them when there is a choice (several NVIDIA cards) or when none is
  suitable, with the reason for each. }

procedure AddCard(const Text: String; Index: Integer; Ok: Boolean);
var
  N: Integer;
begin
  N := GetArrayLength(GpuText);
  SetArrayLength(GpuText, N + 1);
  SetArrayLength(GpuIndex, N + 1);
  SetArrayLength(GpuOk, N + 1);
  GpuText[N] := Text;
  GpuIndex[N] := Index;
  GpuOk[N] := Ok;
  if Index >= 0 then
    NvidiaCount := NvidiaCount + 1;
  if Ok then
    SuitableCount := SuitableCount + 1;
end;

{ The display adapters Windows knows, for the page when no NVIDIA card answers (Intel, AMD...) }
procedure AddOtherAdapters;
var
  Keys: TArrayOfString;
  I: Integer;
  Name, Base: String;
begin
  Base := 'SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}';
  if RegGetSubkeyNames(HKLM, Base, Keys) then
    for I := 0 to GetArrayLength(Keys) - 1 do
      if RegQueryStringValue(HKLM, Base + '\' + Keys[I], 'DriverDesc', Name) and (Pos('NVIDIA', Uppercase(Name)) = 0) then
        AddCard(Name + ': not an NVIDIA card', -1, False);
end;

procedure FindCards;
var
  Code, I, Mem, Major: Integer;
  Output: TExecOutput;
  Smi, L, Name, Driver, Why: String;
  Fields: TArrayOfString;
begin
  { the driver puts nvidia-smi in the 64-bit System32 (the sys constant in 64-bit install mode); a bare name is the fallback }
  Smi := ExpandConstant('{sys}\nvidia-smi.exe');
  if not FileExists(Smi) then
    Smi := 'nvidia-smi.exe';
  if ExecAndCaptureOutput(Smi, '--query-gpu=index,name,memory.total,driver_version --format=csv,noheader,nounits', '',
       SW_SHOWNORMAL, ewWaitUntilTerminated, Code, Output) and (Code = 0) then
    for I := 0 to GetArrayLength(Output.StdOut) - 1 do
    begin
      L := Trim(Output.StdOut[I]);
      if L = '' then Continue;
      Fields := StringSplit(L, [','], stAll);
      if GetArrayLength(Fields) < 4 then Continue;
      Name := Trim(Fields[1]);
      Mem := StrToIntDef(Trim(Fields[2]), 0);
      Driver := Trim(Fields[3]);
      Major := StrToIntDef(Copy(Driver, 1, Pos('.', Driver) - 1), 0);
      Why := '';
      if Mem < 7600 then
        Why := ': ' + IntToStr((Mem + 512) div 1024) + ' GB, the server needs 8'
      else if (Major > 0) and (Major < 570) then
        Why := ': driver ' + Driver + ', the server needs 570 or newer (update it from nvidia.com)';
      AddCard(Name + ', ' + IntToStr((Mem + 512) div 1024) + ' GB, driver ' + Driver + Why, StrToIntDef(Trim(Fields[0]), I), Why = '');
      Log('graphics card ' + Trim(Fields[0]) + ': ' + L);
    end;
  if SuitableCount = 0 then
    AddOtherAdapters;
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not Switch('SKIPGPUCHECK') then
    FindCards;
end;

function ChosenGpu: String;
var
  I: Integer;
begin
  Result := '';
  if NvidiaCount > 1 then
    for I := 0 to GetArrayLength(GpuText) - 1 do
      if GpuPage.Values[I] and GpuOk[I] then
        Result := IntToStr(GpuIndex[I]);
end;

{ ---- The languages page: the languages of the books, each with the models it needs. }

function VoiceIndex(const Voice: String): Integer;
var
  V: Integer;
begin
  Result := -1;
  for V := 0 to GetArrayLength(VoiceName) - 1 do
    if VoiceName[V] = Voice then
      Result := V;
end;

{ One short line per language; the models are named in the box under the list }
function LangLabel(I: Integer): String;
var
  Notes: String;
begin
  Notes := '';
  if not LangTested[I] then
    Notes := 'new';
  if LangVoice[I] = '' then
    Notes := Notes + '; syncs only, not read aloud'
  else if LangMade[I] then
    Notes := Notes + '; narrator made on your PC';
  if Copy(Notes, 1, 2) = '; ' then
    Notes := Copy(Notes, 3, Length(Notes));
  Result := LangName[I];
  if Notes <> '' then
    Result := Result + '   (' + Notes + ')';
end;

function ChosenLanguages: String;
var
  I: Integer;
begin
  Result := '';
  for I := 0 to GetArrayLength(LangCode) - 1 do
    if LangPage.Values[I] then
    begin
      if Result <> '' then Result := Result + ',';
      Result := Result + LangCode[I];
    end;
end;

{ The ticked languages whose narrator is made on this computer, by name, or '' }
function MadeLanguages: String;
var
  I: Integer;
begin
  Result := '';
  for I := 0 to GetArrayLength(LangCode) - 1 do
    if LangPage.Values[I] and LangMade[I] then
    begin
      if Result <> '' then Result := Result + ', ';
      Result := Result + LangName[I];
    end;
end;

{ GB in tenths for the ticked languages: the voice models they need, once each, and a word-timing model each }
procedure LanguageNeeds(var Env10, Models10: Integer);
var
  I, V: Integer;
  Voices: String;
begin
  Env10 := 48;     { the server's own environment }
  Models10 := 15;  { Whisper }
  Voices := ',';
  for I := 0 to GetArrayLength(LangCode) - 1 do
    if LangPage.Values[I] then
    begin
      Models10 := Models10 + Aligner10;
      if (LangVoice[I] <> '') and (Pos(',' + LangVoice[I] + ',', Voices) = 0) then
      begin
        Voices := Voices + LangVoice[I] + ',';
        V := VoiceIndex(LangVoice[I]);
        Env10 := Env10 + VoiceEnv10[V];
        Models10 := Models10 + VoiceModel10[V];
      end;
    end;
end;

function Tenths(N: Integer): String;
begin
  Result := IntToStr(N div 10);
  if N mod 10 <> 0 then
    Result := Result + '.' + IntToStr(N mod 10);
end;

{ The box under the list: the size, then every model the ticked languages use }
procedure UpdateLanguageSize(Sender: TObject);
var
  Env10, Models10, I, V: Integer;
  Text, Who: String;
begin
  LanguageNeeds(Env10, Models10);
  if ChosenLanguages = '' then
  begin
    LangDetails.Text := 'Tick at least one language.';
    Exit;
  end;
  Text := 'Space on disk: about ' + Tenths(Env10 + Models10) + ' GB (' + Tenths(Env10) + ' GB of software, ' +
    Tenths(Models10) + ' GB of models)' + #13#10#13#10 +
    'Voices that read stories aloud:';
  for V := 0 to GetArrayLength(VoiceName) - 1 do
  begin
    Who := '';
    for I := 0 to GetArrayLength(LangCode) - 1 do
      if LangPage.Values[I] and (LangVoice[I] = VoiceName[V]) then
      begin
        if Who <> '' then Who := Who + ', ';
        Who := Who + LangName[I];
      end;
    if Who <> '' then
      Text := Text + #13#10 + '    ' + Who + ':  ' + VoiceLabel[V];
  end;
  Text := Text + #13#10#13#10 + 'Listening to the audiobook:' + #13#10 + '    All languages:  Whisper turbo (OpenAI)' + #13#10#13#10 +
    'Matching each word to its moment in the audio:';
  for I := 0 to GetArrayLength(LangCode) - 1 do
    if LangPage.Values[I] then
      Text := Text + #13#10 + '    ' + LangName[I] + ':  ' + LangAligner[I];
  LangDetails.Text := Text;
end;

{ Ticked when the page first shows: the languages already installed; on a new install, those of /LANGUAGES=,
  or English and the language Windows is in }
procedure FillLanguagePage;
var
  I: Integer;
  Current: String;
begin
  Current := ExpandConstant('{param:LANGUAGES|}');
  if Current = '' then
    Current := SettingNamed(ExpandConstant('{app}'), 'RACCONTAMI_LANGUAGES');
  if (Current = '') and not IsNewInstall then
    Current := 'en,it';  { a server installed before languages could be chosen }
  for I := 0 to GetArrayLength(LangCode) - 1 do
    if Current <> '' then
      LangPage.Values[I] := Pos(',' + LangCode[I] + ',', ',' + Lowercase(Current) + ',') > 0
    else
      LangPage.Values[I] := (LangCode[I] = 'en') or (LangWindows[I] = (GetUILanguage and $3FF));
  { an update skips the folder page (the folder is found by itself): say here which install it updates }
  if not IsNewInstall then
    LangPage.Description := 'Updating the server in ' + ExpandConstant('{app}');
  UpdateLanguageSize(nil);
end;

{ The ticked languages whose narrator is made on this computer, by name: those that have one already
  (Made = True) or those that do not yet }
function NarratorLanguages(Made: Boolean): String;
var
  I: Integer;
begin
  Result := '';
  for I := 0 to GetArrayLength(LangCode) - 1 do
    if LangPage.Values[I] and LangMade[I] and
       (FileExists(ExpandConstant('{app}\server-data\narrators\voxcpm2_') + LangCode[I] + '_ref.wav') = Made) then
    begin
      if Result <> '' then Result := Result + ', ';
      Result := Result + LangName[I];
    end;
end;

{ A narrator already made on this computer for one of the ticked languages }
function NarratorsExist: Boolean;
begin
  Result := NarratorLanguages(True) <> '';
end;

{ The narrator page says what will happen: which narrators are made, which are kept }
procedure SayNarrators;
var
  ToMake, Have, Text: String;
begin
  ToMake := NarratorLanguages(False);
  Have := NarratorLanguages(True);
  if ToMake <> '' then
  begin
    NarratorPage.Description := 'A narrator will be made on this computer for: ' + ToMake;
    Text := 'VoxCPM2 makes it on the graphics card from the description below (written in any language). ' +
      'This takes a few minutes, after the downloads.';
  end
  else
  begin
    NarratorPage.Description := 'Already made on this computer: ' + Have;
    Text := 'The narrator you have is kept. To replace it, tick the box below: VoxCPM2 then makes a new one from ' +
      'the description (a few minutes on the graphics card).';
  end;
  if (ToMake <> '') and (Have <> '') then
    Text := Text + ' Already made and kept: ' + Have + '.';
  NarratorPage.SubCaptionLabel.Caption := Text;
end;

procedure InitializeWizard;
var
  Note: String;
  I: Integer;
begin
  { graphics cards: shown when there is a choice, or when none is suitable }
  GpuPage := CreateInputOptionPage(wpSelectDir, 'Graphics card', 'The NVIDIA card the server works on',
    'The server needs an NVIDIA graphics card with at least 8 GB of memory and a driver of version 570 or newer.', True, True);
  for I := 0 to GetArrayLength(GpuText) - 1 do
  begin
    GpuPage.Add(GpuText[I]);
    GpuPage.CheckListBox.ItemEnabled[I] := GpuOk[I];
  end;
  for I := GetArrayLength(GpuText) - 1 downto 0 do
    if GpuOk[I] then
      GpuPage.Values[I] := True;  { the first suitable card, unless one is ticked below }
  if SuitableCount = 0 then
    GpuPage.SubCaptionLabel.Caption := 'No suitable graphics card was found on this computer, so the server cannot run here. ' +
      'The server needs an NVIDIA card with at least 8 GB of memory and a driver of version 570 or newer. Found:';

  Note := 'The models can go on another drive. Click Next to keep them in the server''s folder, or choose another folder.';
  if GetEnv('HF_HOME') <> '' then
    Note := Note + #13#10#13#10 + 'HF_HOME is set on this computer: with the usual folder, the Hugging Face models (nearly all of them) go to ' +
      GetEnv('HF_HOME') + '; with another folder, all the models go there.';
  ModelsPage := CreateInputDirPage(GpuPage.ID, 'Where should the models go?', 'The speech and voice models the server downloads',
    Note, False, 'raccontami-models');  { the folder picker then offers "Make New Folder", with this name }
  ModelsPage.Add('');
  ModelsPage.Values[0] := ExpandConstant('{param:MODELSDIR|}');  { a scripted install: /MODELSDIR=E:\models }

  FillLanguages;
  LangPage := CreateInputOptionPage(ModelsPage.ID, 'Which languages?', 'The languages of your books',
    'Tick the languages of your books: only the models they need are downloaded. You can change this later, here or on ' +
    'the server''s page. New: not yet tried on whole books.',
    False, True);
  for I := 0 to GetArrayLength(LangCode) - 1 do
    LangPage.Add(LangLabel(I));
  LangPage.CheckListBox.OnClickCheck := @UpdateLanguageSize;
  { the list and the box of sizes and models under it share the page about evenly }
  LangDetails := TNewMemo.Create(LangPage);
  LangDetails.Parent := LangPage.Surface;
  LangDetails.Height := (LangPage.SurfaceHeight - LangPage.CheckListBox.Top) * 9 div 20;
  LangPage.CheckListBox.Height := LangPage.SurfaceHeight - LangPage.CheckListBox.Top - LangDetails.Height - ScaleY(6);
  LangDetails.Top := LangPage.CheckListBox.Top + LangPage.CheckListBox.Height + ScaleY(6);
  LangDetails.Width := LangPage.SurfaceWidth;
  LangDetails.ReadOnly := True;
  LangDetails.ScrollBars := ssVertical;
  LangDetails.WordWrap := True;

  { how a narrator made on this computer sounds: the user describes it }
  NarratorPage := CreateInputQueryPage(LangPage.ID, 'How should the narrator sound?', 'A narrator is made on this computer',
    'Some of the languages ticked have no narrator yet: VoxCPM2 makes one on the graphics card, from a description of the ' +
    'voice (in any language). This takes a few minutes, after the downloads.');
  NarratorPage.Add('Description of the voice:', False);
  NarratorPage.Values[0] := ExpandConstant('{param:NARRATOR|}');
  if NarratorPage.Values[0] = '' then
    NarratorPage.Values[0] := DefaultNarrator;
  RemakeBox := TNewCheckBox.Create(NarratorPage);
  RemakeBox.Parent := NarratorPage.Surface;
  RemakeBox.Top := NarratorPage.Edits[0].Top + NarratorPage.Edits[0].Height + ScaleY(16);
  RemakeBox.Width := NarratorPage.SurfaceWidth;
  RemakeBox.Caption := 'Replace the narrators already made with new ones from this description';
  RemakeBox.Visible := False;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  { the graphics card is asked when there is a choice, or shown when none is suitable }
  if PageID = GpuPage.ID then
    Result := Switch('SKIPGPUCHECK') or ((NvidiaCount <= 1) and (SuitableCount = 1));
  { the models folder is asked once, on a new install; later runs use the one in settings.txt }
  if PageID = ModelsPage.ID then
    Result := (not IsNewInstall) or (GetEnv('RACCONTAMI_MODELS') <> '');
  if PageID = LangPage.ID then
    Result := GetEnv('RACCONTAMI_LANGUAGES') <> '';  { set on the computer: it wins anyway }
  if PageID = NarratorPage.ID then
    Result := MadeLanguages = '';
end;
{ An update: this installer found the server already installed (the folder page is skipped then). Its
  texts then say "update" instead of "setup" and "install". }
function IsUpdate: Boolean;
begin
  Result := WizardForm.PrevAppDir <> '';
end;

procedure SayUpdate(CurPageID: Integer);
begin
  WizardForm.Caption := 'Update - {#AppTitle} {#AppVersion}';
  case CurPageID of
    wpReady:
      begin
        WizardForm.PageNameLabel.Caption := 'Ready to update';
        WizardForm.PageDescriptionLabel.Caption := 'The installer is ready to update the server in ' + WizardDirValue + '.';
        WizardForm.ReadyLabel.Caption := 'Click Update to continue, or Back to change the languages.';
        WizardForm.NextButton.Caption := 'Update';
      end;
    wpInstalling:
      begin
        WizardForm.PageNameLabel.Caption := 'Updating';
        WizardForm.PageDescriptionLabel.Caption := 'Please wait while the server in ' + WizardDirValue + ' is updated.';
      end;
    wpFinished:
      begin
        WizardForm.FinishedHeadingLabel.Caption := 'The Raccontami server is updated';
        WizardForm.FinishedLabel.Caption := 'The update is finished. Your settings, jobs and the phone''s pairing were kept.';
      end;
  end;
end;

{ The question when Cancel is clicked, in the words of an update }
procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if IsUpdate then
  begin
    Confirm := False;
    Cancel := MsgBox('The update is not finished. You can open the installer again at another time to finish it.' + #13#10#13#10 +
      'Stop the update?', mbConfirmation, MB_YESNO) = IDYES;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if IsUpdate then
    SayUpdate(CurPageID);
  if CurPageID = ModelsPage.ID then
    if (ModelsPage.Values[0] = '') or (ModelsPage.Values[0] = ModelsPageDefault) then
    begin
      ModelsPageDefault := AddBackslash(WizardDirValue) + 'models';
      ModelsPage.Values[0] := ModelsPageDefault;
    end;
  if (CurPageID = LangPage.ID) and not LangPageFilled then
  begin
    FillLanguagePage;
    LangPageFilled := True;
  end;
  if CurPageID = NarratorPage.ID then
  begin
    SayNarrators;
    { on an update with narrators already made: they are kept, unless new ones are asked for }
    RemakeBox.Visible := NarratorsExist;
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

{ Free space on a new install, per drive: the Python packages in the server's folder, the models where they go }
function EnoughSpace: Boolean;
var
  HomeDrive, ModelsDrive, Models: String;
  Env10, Models10: Integer;
begin
  Result := True;
  LanguageNeeds(Env10, Models10);
  HomeDrive := ExtractFileDrive(WizardDirValue);
  Models := ModelsPage.Values[0];
  if Models = '' then
    Models := AddBackslash(WizardDirValue) + 'models';
  ModelsDrive := ExtractFileDrive(Models);
  { with the usual folder, a HF_HOME set on the computer keeps nearly all of the models }
  if (CompareText(RemoveBackslash(Models), RemoveBackslash(AddBackslash(WizardDirValue) + 'models')) = 0) and (GetEnv('HF_HOME') <> '') then
    ModelsDrive := ExtractFileDrive(GetEnv('HF_HOME'));
  if CompareText(HomeDrive, ModelsDrive) = 0 then
  begin
    if GB(HomeDrive) * 10 < Env10 + Models10 then
    begin
      SuppressibleMsgBox('These languages need about ' + Tenths(Env10 + Models10) + ' GB on ' + HomeDrive + ' and it has ' +
        IntToStr(GB(HomeDrive)) + ' GB free. Free some space, tick fewer languages, or choose folders on another drive.', mbError, MB_OK, IDOK);
      Result := False;
    end;
  end else if GB(HomeDrive) * 10 < Env10 then
  begin
    SuppressibleMsgBox('The Python packages need about ' + Tenths(Env10) + ' GB on ' + HomeDrive + ' and it has ' + IntToStr(GB(HomeDrive)) +
      ' GB free. Free some space, or choose another folder for the server.', mbError, MB_OK, IDOK);
    Result := False;
  end else if GB(ModelsDrive) * 10 < Models10 then
  begin
    SuppressibleMsgBox('The models need about ' + Tenths(Models10) + ' GB on ' + ModelsDrive + ' and it has ' + IntToStr(GB(ModelsDrive)) +
      ' GB free. Free some space, tick fewer languages, or choose another folder for the models.', mbError, MB_OK, IDOK);
    Result := False;
  end;
end;

{ The languages installed before (settings.txt; English and Italian on a server from before languages could
  be chosen) that are not ticked now, by name, or '' }
function UntickedLanguages: String;
var
  I: Integer;
  Before: String;
begin
  Result := '';
  Before := SettingNamed(ExpandConstant('{app}'), 'RACCONTAMI_LANGUAGES');
  if Before = '' then
    Before := 'en,it';
  for I := 0 to GetArrayLength(LangCode) - 1 do
    if (not LangPage.Values[I]) and (Pos(',' + LangCode[I] + ',', ',' + Lowercase(Before) + ',') > 0) then
    begin
      if Result <> '' then Result := Result + ', ';
      Result := Result + LangName[I];
    end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = GpuPage.ID) and (SuitableCount = 0) then
  begin
    SuppressibleMsgBox('The server cannot run on this computer: it needs an NVIDIA graphics card with at least 8 GB of memory ' +
      'and a driver of version 570 or newer. If the card is there, install its latest driver from nvidia.com and open this ' +
      'installer again.', mbCriticalError, MB_OK, IDOK);
    Result := False;
  end;
  if (CurPageID = NarratorPage.ID) and (Trim(NarratorPage.Values[0]) = '') then
  begin
    SuppressibleMsgBox('Describe the voice, or keep the description that was there.', mbError, MB_OK, IDOK);
    Result := False;
  end;
  if CurPageID = LangPage.ID then
  begin
    if ChosenLanguages = '' then
    begin
      SuppressibleMsgBox('Tick at least one language.', mbError, MB_OK, IDOK);
      Result := False;
    end else if IsNewInstall then
      Result := EnoughSpace
    else if UntickedLanguages <> '' then
      { languages installed before and unticked now: switched off either way; their files go only on yes }
      RemoveUnticked := SuppressibleMsgBox('These languages will be removed: ' + UntickedLanguages + '.' + #13#10#13#10 +
        'Delete their files too? Their word-timing models and narrators made on this computer are deleted, and the ' +
        'voice models no other language needs. No keeps the files, so the languages can be ticked again without ' +
        'downloading them.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES;
  end;
end;

function IsPython(const Name: String): Boolean;
begin
  Result := Pos('python', Lowercase(Name)) = 1;
end;

{ The server's port. A port already named (settings.txt, the computer, /PORT=) is kept. Otherwise 8765, or,
  when another program holds 8765, the next free one. A Python program on the port may be the server itself:
  it is never moved around without asking. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Named, Requested, Pid, P: Integer;
  Name: String;
begin
  Result := '';
  Named := PortNamed(ExpandConstant('{app}'));
  Requested := StrToIntDef(ExpandConstant('{param:PORT|0}'), 0);
  PortChosenNow := False;
  if Named > 0 then
    ServerPort := Named
  else if Requested > 0 then
  begin
    ServerPort := Requested;
    PortChosenNow := Requested <> 8765;
  end else
    ServerPort := 8765;
  Pid := ListenerPid(ServerPort);
  if Pid = 0 then
    Exit;
  Name := ProgramName(Pid);
  if Name = '' then
    Name := 'another program';
  if (Named > 0) or (Requested > 0) then
  begin
    if IsPython(Name) then
      Result := 'Port ' + IntToStr(ServerPort) + ' is in use by ' + Name + ', probably the Raccontami server. Stop it first: its icon ' +
        'next to the clock, Stop the server. Then click Back and Next.'
    else
      SuppressibleMsgBox('Port ' + IntToStr(ServerPort) + ', the server''s port, is used by ' + Name + '. The server can start only when ' +
        'that program stops, or with another port: change RACCONTAMI_PORT in settings.txt.', mbInformation, MB_OK, IDOK);
    Exit;
  end;
  if IsPython(Name) then
    if WizardSilent or (MsgBox('Port 8765 is used by ' + Name + '.' + #13#10#13#10 +
         'If that is the Raccontami server, click No, stop it (its icon next to the clock, Stop the server), then click Back and Next.' + #13#10#13#10 +
         'If it is another program, click Yes: the server will use the next free port.', mbConfirmation, MB_YESNO) = IDNO) then
    begin
      Result := 'Port 8765 is in use by ' + Name + '. If the Raccontami server is running, stop it (its icon next to the clock, ' +
        'Stop the server), then click Back and Next.';
      Exit;
    end;
  for P := 8766 to 8799 do
    if ListenerPid(P) = 0 then
    begin
      ServerPort := P;
      PortChosenNow := True;
      SuppressibleMsgBox('Port 8765 is used by ' + Name + ', so the server will use port ' + IntToStr(P) + '.' + #13#10#13#10 +
        'The app''s "Search local network" looks on port 8765 for now: on the phone, type the address the server''s window ' +
        'shows (it ends in :' + IntToStr(P) + ').', mbInformation, MB_OK, IDOK);
      Exit;
    end;
  Result := 'Ports 8765 to 8799 are all in use. Free one, or set RACCONTAMI_PORT in settings.txt, then open this installer again.';
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
  Params, Models, Description: String;
  Code: Integer;
begin
  Params := '-u ' + AddQuotes(ExpandConstant('{app}\raccontami-server\install\install.py')) +
    ' --home ' + QuoteFolder(ExpandConstant('{app}')) + ' --pause-on-error';
  Models := ModelsPage.Values[0];
  if IsNewInstall and (GetEnv('RACCONTAMI_MODELS') = '') and (Models <> '') then
    Params := Params + ' --models ' + QuoteFolder(Models);
  if PortChosenNow then
    Params := Params + ' --port ' + IntToStr(ServerPort);
  if (GetEnv('RACCONTAMI_LANGUAGES') = '') and (ChosenLanguages <> '') then
    Params := Params + ' --languages ' + ChosenLanguages;
  if ChosenGpu <> '' then
    Params := Params + ' --gpus ' + ChosenGpu;
  if RemoveUnticked then
    Params := Params + ' --remove-unticked';
  if MadeLanguages <> '' then
  begin
    { a quote would end the argument early: the description goes without them }
    Description := NarratorPage.Values[0];
    StringChangeEx(Description, '"', '', True);
    Params := Params + ' --narrator "' + Trim(Description) + '"';
    if RemakeBox.Visible and RemakeBox.Checked then
      Params := Params + ' --remake-narrators';
  end;
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
  if FirewallRuleExists(ServerPort) then
    Exit;
  WizardForm.StatusLabel.Caption := 'Adding the firewall rule (Windows asks for permission)...';
  { Windows' permission prompt names only the program, "Network Command Shell", so say first what it will do }
  if not WizardSilent then
    MsgBox('Windows will now ask for permission to change its firewall.' + #13#10#13#10 +
      'The prompt names "Network Command Shell": that is netsh, Windows'' own firewall tool, published by Microsoft. ' +
      'It adds one rule, "' + RuleName(ServerPort) + '": phones on your home network may reach the Raccontami server on port ' +
      IntToStr(ServerPort) + '. Nothing else changes, and nothing outside your network can reach it.' + #13#10#13#10 +
      'Click Yes in Windows'' prompt. Its "Show more details" shows the exact rule.', mbInformation, MB_OK);
  ShellExec('runas', ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall add rule name="' + RuleName(ServerPort) + '" dir=in action=allow protocol=TCP localport=' +
    IntToStr(ServerPort) + ' remoteip=localsubnet', '', SW_HIDE, ewWaitUntilTerminated, Code);
  if not FirewallRuleExists(ServerPort) then
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

function UninstallPort: Integer;
begin
  Result := PortNamed(ExpandConstant('{app}'));
  if Result <= 0 then
    Result := 8765;
end;

function InitializeUninstall: Boolean;
var
  Name: String;
begin
  Result := True;
  Name := ProgramName(ListenerPid(UninstallPort));
  if IsPython(Name) then
  begin
    SuppressibleMsgBox('Port ' + IntToStr(UninstallPort) + ' is in use by ' + Name + ': the Raccontami server seems to be running. ' +
      'Stop it first: its icon next to the clock, Stop the server. Then uninstall again.', mbError, MB_OK, IDOK);
    Result := False;
  end;
end;

{ The models folder settings.txt names, or '' }
function ModelsFolderNamed(const Home: String): String;
begin
  Result := SettingNamed(Home, 'RACCONTAMI_MODELS');
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
  if FirewallRuleExists(UninstallPort) then
    if SuppressibleMsgBox('Remove the firewall rule "' + RuleName(UninstallPort) + '"? Windows asks for permission (Network Command Shell, ' +
         'Windows'' own firewall tool).', mbConfirmation, MB_YESNO, IDNO) = IDYES then
      ShellExec('runas', ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="' + RuleName(UninstallPort) + '"', '',
        SW_HIDE, ewWaitUntilTerminated, Code);
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
