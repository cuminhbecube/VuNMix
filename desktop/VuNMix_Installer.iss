#define BuildVersion GetEnv("VERSION")
#if BuildVersion == ""
  #define BuildVersion "dev"
#endif

[Setup]
AppId={{5C16C978-B70E-40F1-B733-1492DA3DCA28}
AppName=VuNMix
AppVersion={#BuildVersion}
AppPublisher=VuNL
DefaultDirName={autopf}\VuNMix
DefaultGroupName=VuNMix
OutputDir=setup_output
OutputBaseFilename=VuNMix_Setup
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=yes
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\VuNMix.exe
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\VuNMix\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\VuNMix"; Filename: "{app}\VuNMix.exe"; IconFilename: "{app}\VuNMix.exe"
Name: "{group}\Uninstall VuNMix"; Filename: "{uninstallexe}"
Name: "{autodesktop}\VuNMix"; Filename: "{app}\VuNMix.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VuNMix.exe"; Description: "Launch VuNMix"; Flags: nowait runasoriginaluser

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { Older VuNMix versions can launch this installer but remain running.
    Force only VuNMix.exe closed before files are replaced. The installer
    itself has a versioned setup filename, so it is not matched here. }
  Exec(
    ExpandConstant('{cmd}'),
    '/C taskkill /F /IM VuNMix.exe >nul 2>&1',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Sleep(300);
  Result := '';
end;
