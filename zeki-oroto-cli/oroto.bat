@echo off
REM Oroto CLI Tool - Global Command
REM This batch file allows running Oroto from anywhere in the system

REM Get the directory where this batch file is located
set "OROTO_DIR=%~dp0"

REM Run the Python script from installation directory, but keep the user's current working directory
setlocal
set "SCRIPT=%OROTO_DIR%main.py"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py "%SCRIPT%" %*
) else (
    python "%SCRIPT%" %*
)
endlocal