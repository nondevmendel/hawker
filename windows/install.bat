@echo off
REM ============================================================
REM  Hawker — simple Python installer (no exe bundling)
REM  Use this if Python 3.10+ is already installed.
REM
REM  For a standalone installer that doesn't require Python,
REM  run build.bat instead to produce Hawker.exe + HawkerSetup.exe
REM ============================================================

setlocal

set HAWKER_DIR=%APPDATA%\Hawker
set INSTALL_DIR=%APPDATA%\Hawker\app

echo.
echo  ================================
echo   Hawker Installer (Python mode)
echo  ================================
echo.

REM -- Python check
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3 not found.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Python %PYVER% found.

REM -- Create data + app directories
if not exist "%HAWKER_DIR%" mkdir "%HAWKER_DIR%"
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

REM -- Copy scripts
echo Copying files to %INSTALL_DIR%...
copy /Y "%~dp0daemon_win.py" "%INSTALL_DIR%\" >nul
copy /Y "%~dp0tray_win.py"   "%INSTALL_DIR%\" >nul

REM -- Install dependencies
echo Installing Python dependencies...
pip install pillow mss pystray uiautomation
if errorlevel 1 (
    echo ERROR: pip install failed. Check your internet connection.
    pause
    exit /b 1
)

REM -- Write hawker.env if it doesn't exist yet
if not exist "%HAWKER_DIR%\hawker.env" (
    echo.
    set /p API_URL="Enter your Hawker API URL [https://hawker-flax.vercel.app]: "
    if "!API_URL!"=="" set API_URL=https://hawker-flax.vercel.app
    set /p API_KEY="Enter your Hawker API Key: "
    (
        echo HAWKER_API_URL=!API_URL!
        echo HAWKER_API_KEY=!API_KEY!
    ) > "%HAWKER_DIR%\hawker.env"
    echo hawker.env written.
)

REM -- Create a launcher script in the install dir
set LAUNCHER=%INSTALL_DIR%\launch.bat
(
    echo @echo off
    echo start "" pythonw "%INSTALL_DIR%\tray_win.py"
) > "%LAUNCHER%"

REM -- Create Start Menu shortcut via PowerShell
set SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Hawker.lnk
powershell -NoProfile -Command ^
  "$ws = New-Object -COM WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = 'pythonw.exe'; $s.Arguments = '\"%INSTALL_DIR%\tray_win.py\"'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Save()"
echo Start Menu shortcut created.

REM -- Ask about startup
echo.
set /p STARTUP="Launch Hawker automatically at login? (y/n): "
if /i "%STARTUP%"=="y" (
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" ^
        /v "Hawker" /t REG_SZ /d "pythonw \"%INSTALL_DIR%\tray_win.py\"" /f >nul
    echo Startup entry added.
)

echo.
echo  Installation complete!
echo  Run Hawker from the Start Menu, or double-click:
echo    %INSTALL_DIR%\launch.bat
echo.
echo  Config file: %HAWKER_DIR%\hawker.env
echo  Log file:    %HAWKER_DIR%\hawker.log
echo  Screenshots: %HAWKER_DIR%\screenshots\
echo.

set /p LAUNCH="Launch Hawker now? (y/n): "
if /i "%LAUNCH%"=="y" (
    start "" pythonw "%INSTALL_DIR%\tray_win.py"
)

endlocal
