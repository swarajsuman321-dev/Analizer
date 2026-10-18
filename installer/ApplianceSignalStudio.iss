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
; The marker is installed with the payload and also included in staging.
Source: "installed-layout.json"; DestDir: "{app}\versions\{#AppVersion}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Appliance Signal Studio"; Filename: "{app}\versions\{#AppVersion}\ApplianceSignalStudio.exe"; AppUserModelID: "ApplianceSignalStudio.Workbench"
Name: "{autodesktop}\Appliance Signal Studio"; Filename: "{app}\versions\{#AppVersion}\ApplianceSignalStudio.exe"; Tasks: desktopicon; AppUserModelID: "ApplianceSignalStudio.Workbench"

[Run]
Filename: "{app}\versions\{#AppVersion}\ApplianceSignalStudio.exe"; Description: "Launch Appliance Signal Studio"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  Runtime, ReportPath: String;
begin
  Result := '';
  #ifdef FailHealthCheck
  Result := 'Simulated runtime failure for the isolated upgrade test.';
  Exit;
  #endif
  try
    // Stage the complete payload before changing installed files.
    // Temporary extraction keeps the literal app constant beneath the temp root.
    // A nonempty result is a hard stop; AfterInstall exceptions are not.
    ExtractTemporaryFiles('*');
    Runtime := ExpandConstant('{tmp}\') + '{app}\versions\{#AppVersion}\ApplianceSignalStudio.exe';
    ReportPath := ExpandConstant('{localappdata}\ApplianceSignalStudio\InstallerLogs\check-{#AppVersion}.json');
    ForceDirectories(ExtractFileDir(ReportPath));
    DeleteFile(ReportPath);
    if not Exec(Runtime, '{#HealthArguments} --report "' + ReportPath + '"',
      ExtractFileDir(Runtime), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      Result := 'The staged runtime could not start. The existing installation is unchanged.'
    else if (ResultCode <> 0) or not FileExists(ReportPath) then
      Result := 'Runtime verification failed. The existing installation is unchanged. See ' + ReportPath;
  except
    Result := 'Could not verify the complete runtime: ' + GetExceptionMessage;
  end;
  if Result <> '' then Log(Result);
end;
