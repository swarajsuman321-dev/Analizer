; Build with scripts/build_installer.py from the tested one-folder payload.
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef PayloadDir
  #error PayloadDir is required
#endif
#ifndef OutputBase
  #define OutputBase "ApplianceSignalStudio-Setup-" + AppVersion
#endif
#ifndef HealthArguments
  #define HealthArguments "--installation-check"
#endif

[Setup]
AppId={{A63EB095-928B-4A47-943A-E0C289DA916C}
AppName=Appliance Signal Studio
AppVersion={#AppVersion}
AppPublisher=Appliance Signal Studio project
AppPublisherURL=https://github.com/swarajsuman321-dev/Analizer
DefaultDirName={localappdata}\Programs\ApplianceSignalStudio
DefaultGroupName=Appliance Signal Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename={#OutputBase}
SetupIconFile=..\app_icon.ico
UninstallDisplayIcon={app}\versions\{#AppVersion}\ApplianceSignalStudio.exe
UninstallDisplayName=Appliance Signal Studio
WizardStyle=modern
Compression=lzma2/fast
SolidCompression=yes
CloseApplications=no
RestartApplications=no
AppMutex=Local\ApplianceSignalStudio.Workbench
UsePreviousAppDir=yes
DisableWelcomePage=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}\versions\{#AppVersion}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Check the newly copied runtime before shortcuts and installation registration.
Source: "installed-layout.json"; DestDir: "{app}\versions\{#AppVersion}"; Flags: ignoreversion; AfterInstall: VerifyRuntime

[Icons]
Name: "{autoprograms}\Appliance Signal Studio"; Filename: "{app}\versions\{#AppVersion}\ApplianceSignalStudio.exe"; AppUserModelID: "ApplianceSignalStudio.Workbench"
Name: "{autodesktop}\Appliance Signal Studio"; Filename: "{app}\versions\{#AppVersion}\ApplianceSignalStudio.exe"; Tasks: desktopicon; AppUserModelID: "ApplianceSignalStudio.Workbench"

[Run]
Filename: "{app}\versions\{#AppVersion}\ApplianceSignalStudio.exe"; Description: "Launch Appliance Signal Studio"; Flags: nowait postinstall skipifsilent

[Code]
procedure VerifyRuntime;
var
  ResultCode: Integer;
  Runtime, ReportPath: String;
begin
  Runtime := ExpandConstant('{app}\versions\{#AppVersion}\ApplianceSignalStudio.exe');
  ReportPath := ExpandConstant('{localappdata}\ApplianceSignalStudio\InstallerLogs\check-{#AppVersion}.json');
  ForceDirectories(ExtractFileDir(ReportPath));
  DeleteFile(ReportPath);
  #ifdef FailHealthCheck
  RaiseException('Simulated runtime failure for the isolated upgrade test.');
  #endif
  if not Exec(Runtime, '{#HealthArguments} --report "' + ReportPath + '"',
    ExtractFileDir(Runtime), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    RaiseException('The installed runtime could not start. Previous versions and your data are retained.');
  if (ResultCode <> 0) or not FileExists(ReportPath) then
    RaiseException('Runtime verification failed. Previous versions and your data are retained. See ' + ReportPath);
end;
