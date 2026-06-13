@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ============================================
echo   ymusic-migrator  (Yandex - YT Music)
echo ============================================
echo.

rem --- pick ONE interpreter for both install and run ---
rem prefer 'python' (already on PATH); fall back to the py launcher
set "PY=python"
where python >nul 2>nul || set "PY=py -3"

echo Using interpreter: %PY%
%PY% --version
echo.

echo [1/2] Installing dependencies (same interpreter)...
%PY% -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
  echo.
  echo  ERROR: pip install failed. Read messages above.
  echo  Try manually:  %PY% -m pip install flask yandex-music ytmusicapi
  echo.
  pause
  exit /b 1
)

echo.
echo [2/2] Starting UI at http://127.0.0.1:5000
%PY% app.py

pause
