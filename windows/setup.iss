; ============================================================
;  Hawker Installer — Inno Setup 6 script
;
;  To compile:
;    iscc setup.iss
;  or open in Inno Setup IDE and press F9.
;
;  Prerequisites:
;    - Run build.bat first to produce dist\Hawker.exe
;    - Inno Setup 6+: https://jrsoftware.org/isinfo.php
; ============================================================

#define AppName      "Hawker"
#define AppVersion   "1.0"
#define AppPublisher "Mendel Rosenberg"
#define AppURL       "https://hawker-flax.vercel.app"
#define AppExeName   "Hawker.exe"
#define DataDir      "{userappdata}\Hawker"

[Setup]
AppId={{8F3A1B2C-4D5E-6F7A-8B9C-0D1E2F3A4B5C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Installer output
OutputDir=installer_output
OutputBaseFilename=HawkerSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; No elevation needed — installs to per-user AppData for config, optional Program Files
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Custom pages
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.ApiUrlLabel=Hawker API URL:
english.ApiKeyLabel=Hawker API Key:
english.ApiPageTitle=Hawker Configuration
english.ApiPageDesc=Enter your Hawker API credentials. Leave blank to configure later.

[Tasks]
Name: "startup"; Description: "Launch Hawker automatically at Windows login"; GroupDescription: "Additional options:"
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Additional options:"

[Files]
; The bundled executable produced by build.bat
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";       Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Launch Hawker after install (non-elevated, in user session)
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; \
    Flags: nowait postinstall skipifsilent

[Registry]
; Launch at startup if the user chose that task
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#AppName}"; \
    ValueData: """{app}\{#AppExeName}"""; \
    Flags: uninsdeletevalue; Tasks: startup

[Code]
// ── Custom wizard page: API credentials ──────────────────────────────────

var
  ApiPage:  TWizardPage;
  UrlEdit:  TEdit;
  KeyEdit:  TEdit;

procedure InitializeWizard;
var
  UrlLabel, KeyLabel: TLabel;
begin
  ApiPage := CreateCustomPage(wpSelectTasks,
    ExpandConstant('{cm:ApiPageTitle}'),
    ExpandConstant('{cm:ApiPageDesc}')
  );

  UrlLabel        := TLabel.Create(WizardForm);
  UrlLabel.Parent := ApiPage.Surface;
  UrlLabel.Left   := 0;
  UrlLabel.Top    := 8;
  UrlLabel.Width  := ApiPage.SurfaceWidth;
  UrlLabel.Caption := ExpandConstant('{cm:ApiUrlLabel}');

  UrlEdit          := TEdit.Create(WizardForm);
  UrlEdit.Parent   := ApiPage.Surface;
  UrlEdit.Left     := 0;
  UrlEdit.Top      := 24;
  UrlEdit.Width    := ApiPage.SurfaceWidth;
  UrlEdit.Text     := 'https://hawker-flax.vercel.app';

  KeyLabel        := TLabel.Create(WizardForm);
  KeyLabel.Parent := ApiPage.Surface;
  KeyLabel.Left   := 0;
  KeyLabel.Top    := 60;
  KeyLabel.Width  := ApiPage.SurfaceWidth;
  KeyLabel.Caption := ExpandConstant('{cm:ApiKeyLabel}');

  KeyEdit          := TEdit.Create(WizardForm);
  KeyEdit.Parent   := ApiPage.Surface;
  KeyEdit.Left     := 0;
  KeyEdit.Top      := 76;
  KeyEdit.Width    := ApiPage.SurfaceWidth;
  KeyEdit.PasswordChar := '*';
end;

// Write hawker.env after installation completes
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataPath, EnvContent: String;
  EnvFile: String;
begin
  if CurStep = ssPostInstall then begin
    DataPath   := ExpandConstant('{userappdata}\Hawker');
    ForceDirectories(DataPath);
    EnvFile    := DataPath + '\hawker.env';
    EnvContent := 'HAWKER_API_URL=' + UrlEdit.Text + #13#10
                + 'HAWKER_API_KEY=' + KeyEdit.Text + #13#10;
    SaveStringToFile(EnvFile, EnvContent, False);
  end;
end;
