; Inno Setup script of HR-System (built by tools/build_windows.py). docs/HR_DELIVERY.md, ADR-HR-004.
; The same HR-System-Setup.exe installs the program on a new PC and updates it on a PC that already has it:
; only the program in Program Files is replaced; the data in %ProgramData%\HR-System is never touched by the
; installer (the program itself takes a verified backup before it moves data to a new data version).

#define MyAppName "HR-System"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Mohamed Fawzy"
#endif
#ifndef AppCopyright
  #define AppCopyright "(c) 2026 Mohamed Fawzy"
#endif

[Setup]
AppId={{3C9A1F52-8E47-4B1D-9F26-5A0D7C84E1B3}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppCopyright={#AppCopyright}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\HR-System
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
DisableDirPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=HR-System-Setup-{#AppVersion}
SetupIconFile=..\build\hr.ico
UninstallDisplayIcon={app}\HR-System.exe
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Start HR-System when Windows starts (recommended on the server computer; it can be switched off later in Settings)"
Name: "desktopicon"; Description: "Put an icon on the desktop"

[Dirs]
; data, backups, settings and the recovery installer: kept when the program is updated or removed
Name: "{commonappdata}\HR-System"; Permissions: users-modify; Flags: uninsneveruninstall
Name: "{commonappdata}\HR-System\data"; Flags: uninsneveruninstall
Name: "{commonappdata}\HR-System\recovery"; Flags: uninsneveruninstall

[Files]
Source: "..\build\hr_main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\HR-System.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\HR-System.exe"; Tasks: desktopicon
Name: "{commonstartup}\{#MyAppName}"; Filename: "{app}\HR-System.exe"; Parameters: "--background"; Tasks: autostart

[Run]
Filename: "{app}\HR-System.exe"; Description: "Open HR-System now"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM HR-System.exe"; Flags: runhidden; RunOnceId: "StopHR"

[Messages]
FinishedLabel=HR-System is installed. Your data is kept in %ProgramData%\HR-System (also after updates and if the program is removed).

[Code]
var
  ExcelPage: TOutputMsgWizardPage;
  OldPage: TInputOptionWizardPage;
  OldDirPage: TInputDirWizardPage;

function DataHome(): String;
begin
  Result := ExpandConstant('{commonappdata}\HR-System');
end;

function HasData(): Boolean;
begin
  Result := FileExists(DataHome() + '\data\hr_journal.db') or FileExists(DataHome() + '\data\history.db');
end;

function ExcelInstalled(): Boolean;
begin
  { Excel is not part of Windows: only protected workbooks need it, so it is explained, never assumed }
  Result := RegKeyExists(HKEY_CLASSES_ROOT, 'Excel.Application\CLSID');
end;

function OldFolderParam(): String;
begin
  Result := ExpandConstant('{param:OLDDATA|}');
end;

procedure InitializeWizard();
begin
  ExcelPage := CreateOutputMsgPage(wpSelectTasks, 'Microsoft Excel',
    'Microsoft Excel was not found on this computer.',
    'HR-System reads ordinary Excel files by itself. Only PROTECTED workbooks (with a company protection or password) ' +
    'need Microsoft Excel on this computer to be opened. You can install Excel later; nothing else changes.');
  OldPage := CreateInputOptionPage(ExcelPage.ID, 'Data of the old attendance program',
    'Was the old HR Attendance Control (the folder with START.bat) used on this computer?',
    'If yes, the installer brings its attendance history into HR-System.', True, False);
  OldPage.Add('No - this is a new computer, or it never had the old program');
  OldPage.Add('Yes - bring the attendance history of the old program');
  OldPage.SelectedValueIndex := 0;
  OldDirPage := CreateInputDirPage(OldPage.ID, 'Data of the old attendance program', 'Where is the folder of the old program?',
    'Choose the folder that contains START.bat. Close the old program first.', False, '');
  OldDirPage.Add('');
  OldDirPage.Values[0] := 'C:\HR-Attendance-Control';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PageID = ExcelPage.ID) and ExcelInstalled() then
    Result := True;
  if (PageID = OldPage.ID) and HasData() then
    Result := True;   { already installed with data: an update, nothing to bring }
  if (PageID = OldDirPage.ID) and (HasData() or (OldPage.SelectedValueIndex <> 1)) then
    Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Old: String;
begin
  Result := True;
  if CurPageID = OldDirPage.ID then
  begin
    Old := RemoveBackslashUnlessRoot(OldDirPage.Values[0]);
    if not FileExists(Old + '\data\history.db') then
    begin
      MsgBox('This folder has no attendance history of the old program (data\history.db was not found).' + #13#10 +
             'Choose the folder that contains START.bat.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { stop the running program so its files can be replaced; every change it makes is one atomic database commit }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM HR-System.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(1000);
  Result := '';
end;

procedure BringOldData(Old: String);
var
  Code: Integer;
begin
  { a copy, never a move: the old folder stays exactly as it was (the rollback line) }
  Exec(ExpandConstant('{sys}\robocopy.exe'), '"' + Old + '\data" "' + DataHome() + '\data" history.db last_result.json /R:2 /W:1 /NFL /NDL /NJH /NJS /NP',
       '', SW_HIDE, ewWaitUntilTerminated, Code);
  if Code >= 8 then
  begin
    DeleteFile(DataHome() + '\data\history.db');
    DeleteFile(DataHome() + '\data\last_result.json');
    MsgBox('Copying the old attendance history failed (code ' + IntToStr(Code) + '). Nothing was brought over; the old program is unchanged.', mbError, MB_OK);
    Exit;
  end;
  if DirExists(Old + '\data\uploads') then
    Exec(ExpandConstant('{sys}\robocopy.exe'), '"' + Old + '\data\uploads" "' + DataHome() + '\data\uploads" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP',
         '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

procedure KeepInstallerForRecovery();
var
  Dir, Exe, Json: String;
begin
  { the program promotes this copy to recovery\known-good only after this version started and verified cleanly }
  Dir := DataHome() + '\recovery\pending';
  DelTree(Dir, True, True, True);
  ForceDirectories(Dir);
  Exe := Dir + '\HR-System-Setup.exe';
  if not FileCopy(ExpandConstant('{srcexe}'), Exe, False) then
    Exit;
  Json := '{"file": "HR-System-Setup.exe", "version": "{#AppVersion}", "sha256": "' + GetSHA256OfFile(Exe) + '"}';
  SaveStringToFile(Dir + '\installer.json', Json, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Old: String;
begin
  if CurStep = ssPostInstall then
  begin
    Old := OldFolderParam();
    if (Old = '') and (OldPage.SelectedValueIndex = 1) then
      Old := RemoveBackslashUnlessRoot(OldDirPage.Values[0]);
    if (Old <> '') and (not HasData()) and FileExists(Old + '\data\history.db') then
      BringOldData(Old);
    KeepInstallerForRecovery();
  end;
end;
