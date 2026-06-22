[Setup]
AppId={{5C16C978-B70E-40F1-B733-1492DA3DCA28}
AppName=VuNMix
AppVersion=0.1
AppPublisher=VuNL
DefaultDirName={autopf}\VuNMix
DefaultGroupName=VuNMix
OutputDir=setup_output
OutputBaseFilename=VuNMix_Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\VuNMix.exe
ArchitecturesInstallIn64BitMode=x64

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist_v7\VuNMix\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\VuNMix"; Filename: "{app}\VuNMix.exe"; IconFilename: "{app}\VuNMix.exe"
Name: "{group}\Uninstall VuNMix"; Filename: "{uninstallexe}"
Name: "{autodesktop}\VuNMix"; Filename: "{app}\VuNMix.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VuNMix.exe"; Description: "Launch VuNMix"; Flags: nowait postinstall skipifsilent
