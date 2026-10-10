; Inno Setup script: wraps PyInstaller's dist\Finder folder into a single
; one-click Windows installer (FinderSetup-<version>.exe).
;
; Build on Windows, after `pyinstaller packaging\finder.spec --noconfirm`:
;   iscc /DAppVersion=1.0.0 packaging\windows\finder.iss
; Output: dist\installer\FinderSetup-<version>.exe
;
; "One click": every wizard page is skipped and no admin rights are needed
; (installs per-user into %LOCALAPPDATA%\Programs\Finder). Everything the app
; needs - Python, Qt, spaCy and its model - is already inside dist\Finder, so
; nothing else is downloaded or installed.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName "Finder"
#define AppPublisher "Ojas Sharma"
#define AppExe "Finder.exe"
#define RootDir "..\.."

[Setup]
; Fixed GUID: lets newer versions upgrade in place and keeps one entry in
; "Installed apps". Never change it.
AppId={{6F3C2A1E-8B4D-4C7A-9E2F-5D1B7A3C9E40}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#RootDir}\dist\installer
OutputBaseFilename=FinderSetup-{#AppVersion}
SetupIconFile={#RootDir}\packaging\icons\finder.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Close a running copy before upgrading, and restart it afterwards.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#RootDir}\dist\Finder\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only the app's own install folder. User settings (%APPDATA%\Finder) and the
; .finder_index folders inside indexed folders are left alone on purpose.
Type: filesandordirs; Name: "{app}"
