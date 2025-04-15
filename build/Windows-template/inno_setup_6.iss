; -- Improve_ImgSLI Inno Setup Script --
; Скрипт для создания установщика Windows для Improve_ImgSLI

#define MyAppName "Improve ImgSLI"
#define MyAppVersion "3.1.0"  ; <-- Укажите вашу версию
#define MyAppPublisher "Loganavter" ; <-- Укажите ваше имя или компанию
#define MyAppURL "https://github.com/Loganavter/Improve-ImgSLI" ; <-- Укажите URL, если есть (опционально)
#define MyAppExeName "Improve_ImgSLI.exe"
#define MyAppSetupName "Improve_ImgSLI_Setup" ; Имя выходного файла установщика

[Setup]
; Общая информация о приложении и установщике
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Папка установки по умолчанию (в Program Files или Program Files (x86))
DefaultDirName={autopf}\{#MyAppName}
; Не спрашивать имя папки в меню Пуск
DisableProgramGroupPage=yes
; Куда сохранить собранный setup.exe (в папку Output рядом со скриптом)
OutputDir=Output
OutputBaseFilename={#MyAppSetupName}
; Сжатие для уменьшения размера установщика
Compression=lzma
SolidCompression=yes
; Требовать права администратора (для записи в Program Files и реестр)
PrivilegesRequired=admin
; Иконка для элемента "Установка и удаление программ" (берется из вашего EXE)
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=33.ico

[Languages]
; Языки интерфейса установщика
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
; Дополнительные задачи при установке (опционально)
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Файлы, которые нужно скопировать. Так как у вас --onefile, нужен только сам EXE.
; Убедитесь, что Improve_ImgSLI.exe находится рядом с этим .iss файлом,
; либо укажите полный или относительный путь к нему.
Source: "{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Примечание: Все зависимости (.dll, .pyd, шрифт и ваши .py модули)
; находятся ВНУТРИ MyAppExeName благодаря --onefile и --add-data/--hidden-import.
; Копировать папку _internal НЕ НУЖНО.

[Icons]
; Создание ярлыков
; Ярлык в меню Пуск
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
; Ярлык на рабочем столе (если выбрана задача "desktopicon")
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Запуск приложения после установки (опционально)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Что удалять при деинсталляции (Inno Setup обычно сам удаляет все из {app})
Type: filesandordirs; Name: "{app}"