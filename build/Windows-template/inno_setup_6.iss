; -- Improve_ImgSLI Inno Setup Script --

#define MyAppName "BlinkTable"
#define MyAppVersion "11.0.0"
#define MyAppPublisher "Loganavter"
#define MyAppURL "https://github.com/Loganavter/Improve-ImgSLI"
#define MyAppExeName "Improve_ImgSLI.exe"
#define MyAppSetupName "Improve_ImgSLI_Setup_v11.0.0"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename={#MyAppSetupName}
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=icons/icon.ico
LicenseFile=..\..\LICENSE
InfoBeforeFile=licenses\WINDOWS_QT_NOTICE.txt
InfoAfterFile=licenses\FFMPEG_NOTICE.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc"; Description: "Associate .blinktable project files with BlinkTable"; GroupDescription: "File associations:"; Flags: checkedonce

[Files]
Source: "..\..\dist\Improve_ImgSLI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "icons\blinktable-file.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "icons\icon.ico"; DestDir: "{app}\icons"; Flags: ignoreversion

[Registry]
Root: HKCU; Subkey: "Software\improve-imgsli\improve-imgsli"; ValueType: string; ValueName: "is_first_run"; ValueData: "true"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\improve-imgsli\improve-imgsli"; Flags: uninsdeletekeyifempty
Root: HKCU; Subkey: "Software\improve-imgsli"; Flags: uninsdeletekeyifempty

; .blinktable → ProgID (HKLM; installer requires admin)
Root: HKLM; Subkey: "Software\Classes\.blinktable"; ValueType: string; ValueData: "BlinkTable.Project"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKLM; Subkey: "Software\Classes\.blinktable"; ValueType: string; ValueName: "Content Type"; ValueData: "application/vnd.blinktable.project+zip"; Tasks: fileassoc
Root: HKLM; Subkey: "Software\Classes\.blinktable\OpenWithProgids"; ValueType: string; ValueName: "BlinkTable.Project"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
; Legacy .imgsli → same ProgID, so projects saved before the rename still open
Root: HKLM; Subkey: "Software\Classes\.imgsli"; ValueType: string; ValueData: "BlinkTable.Project"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKLM; Subkey: "Software\Classes\.imgsli"; ValueType: string; ValueName: "Content Type"; ValueData: "application/x-improve-imgsli"; Tasks: fileassoc
Root: HKLM; Subkey: "Software\Classes\.imgsli\OpenWithProgids"; ValueType: string; ValueName: "BlinkTable.Project"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKLM; Subkey: "Software\Classes\BlinkTable.Project"; ValueType: string; ValueData: "BlinkTable Project"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKLM; Subkey: "Software\Classes\BlinkTable.Project"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "BlinkTable Project"; Tasks: fileassoc
Root: HKLM; Subkey: "Software\Classes\BlinkTable.Project\DefaultIcon"; ValueType: string; ValueData: "{app}\icons\blinktable-file.ico,0"; Tasks: fileassoc
Root: HKLM; Subkey: "Software\Classes\BlinkTable.Project\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassoc

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\{#MyAppName}\Third-Party Licenses"; Filename: notepad.exe; Parameters: """{app}\licenses\WINDOWS_QT_NOTICE.txt"""
Name: "{autoprograms}\{#MyAppName}\Qt Bundle Info"; Filename: notepad.exe; Parameters: """{app}\licenses\Qt_BUNDLE_INFO.txt"""
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"