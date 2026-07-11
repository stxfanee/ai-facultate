#define MyAppName "Co-pilot Facultate"
#define MyAppVersion GetEnv("FACULTY_COPILOT_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "stxfanee"
#define MyAppExeName "Co-pilot Facultate.exe"

[Setup]
AppId={{F3192FAE-2F0D-45C7-8B0C-4E92D9E1F201}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=no
OutputDir=..\..\dist
OutputBaseFilename=Co-pilot Facultate Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\copilot_facultate.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "..\..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
