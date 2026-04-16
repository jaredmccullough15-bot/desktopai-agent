#define MyAppName "Bill Worker"
#ifndef AppVersion
  #define AppVersion "1.0.4"
#endif
#ifndef SourceDir
  #define SourceDir ".\\package-output\\bill-worker"
#endif
#ifndef OutDir
  #define OutDir ".\\package-output\\installer"
#endif

[Setup]
AppId={{D4E9F6A8-8B5F-4A06-BE7C-E8D5FB6E2A21}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher=Bill
DefaultDirName={autopf}\\Bill Worker
DefaultGroupName=Bill Worker
DisableProgramGroupPage=yes
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutDir}
OutputBaseFilename=bill-worker-setup-{#AppVersion}
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SourceDir}\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\\Bill Worker\\Start Bill Worker"; Filename: "{app}\\start-bill-worker.cmd"; WorkingDir: "{app}"
Name: "{autodesktop}\\Start Bill Worker"; Filename: "{app}\\start-bill-worker.cmd"; Tasks: desktopicon; WorkingDir: "{app}"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\\start-bill-worker.cmd"; Description: "Launch Bill Worker now"; Flags: nowait postinstall skipifsilent
