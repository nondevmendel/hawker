@echo off
REM ============================================================
REM  Hawker Windows build script
REM  Bundles tray_win.py + daemon_win.py into a single .exe
REM  using PyInstaller, then optionally compiles the installer.
REM
REM  Requirements (run once):
REM    pip install pyinstaller pillow mss pystray uiautomation
REM  Optional OCR:
REM    pip install pytesseract   (also install Tesseract from GitHub)
REM ============================================================

setlocal

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo [1/3] Installing Python dependencies...
pip install pyinstaller pillow mss pystray uiautomation
if errorlevel 1 goto :err

echo [2/3] Building Hawker.exe with PyInstaller...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name Hawker ^
    --add-data "daemon_win.py;." ^
    tray_win.py
if errorlevel 1 goto :err

echo [3/3] Build complete.
echo   Output: %SCRIPT_DIR%dist\Hawker.exe
echo.

REM Optionally compile the Inno Setup installer (requires Inno Setup 6+)
where iscc >nul 2>&1
if %errorlevel% == 0 (
    echo Compiling installer with Inno Setup...
    iscc setup.iss
    if errorlevel 1 echo Warning: Inno Setup compilation failed.
) else (
    echo Inno Setup not found. To build an installer:
    echo   1. Install Inno Setup from https://jrsoftware.org/isinfo.php
    echo   2. Re-run this script, or run: iscc setup.iss
)

goto :end

:err
echo.
echo BUILD FAILED. Check the output above.
exit /b 1

:end
endlocal
