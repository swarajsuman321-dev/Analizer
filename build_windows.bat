@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Appliance Signal Studio - Windows EXE Builder

if exist ".venv-exe\Scripts\python.exe" goto run_builder

py -3.12 -c "import sys; assert sys.maxsize > 2**32" >nul 2>&1
if not errorlevel 1 (
    py -3.12 -m venv ".venv-exe"
    goto check_venv
)
py -3.13 -c "import sys; assert sys.maxsize > 2**32" >nul 2>&1
if not errorlevel 1 (
    py -3.13 -m venv ".venv-exe"
    goto check_venv
)
py -3.11 -c "import sys; assert sys.maxsize > 2**32" >nul 2>&1
if not errorlevel 1 (
    py -3.11 -m venv ".venv-exe"
    goto check_venv
)
python -c "import sys; assert sys.maxsize > 2**32 and (3,11) <= sys.version_info[:2] <= (3,13)" >nul 2>&1
if not errorlevel 1 (
    python -m venv ".venv-exe"
    goto check_venv
)
echo.
echo Python was not found, or it is not a supported 64-bit version.
echo Install 64-bit Python 3.12 from https://www.python.org/downloads/windows/
echo Then double-click this file again.
pause
exit /b 1

:check_venv
if not exist ".venv-exe\Scripts\python.exe" (
    echo Could not create the build environment. Extract the ZIP to a writable folder.
    pause
    exit /b 1
)

:run_builder
".venv-exe\Scripts\python.exe" "build_exe.py" %*
if errorlevel 1 (
    echo.
    echo Build did not finish. See the error above and build\build.log if it exists.
    pause
    exit /b 1
)
echo.
echo Build completed. The resulting EXE can run without Python installed.
pause
exit /b 0
