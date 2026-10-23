@echo off
rem GRAFIK — jednoklikove spusteni.
rem   8300 = GRAFIK Engine v2 (obrazova sluzba pro vsechny projekty, lokalni FLUX)
rem   5174 = GRAFIK Studio v2 (React, /api -> 8300)
rem   Stary editor v1 je od 2026-10-23 pryc (git tag v1-final).
rem Bezici sluzby nespousti znovu (kontrola portu), takze je bezpecne pustit opakovane.
cd /d "%~dp0"
if not exist logs mkdir logs

netstat -ano | findstr ":8300 " | findstr "LISTENING" >nul
if errorlevel 1 (
  echo Spoustim GRAFIK Engine na portu 8300...
  start "GRAFIK Engine" /min cmd /c "python -m uvicorn engine.app:app --port 8300 --host 127.0.0.1 --access-log >> logs\engine.log 2>&1"
) else (
  echo GRAFIK Engine uz bezi.
)

netstat -ano | findstr ":5174 " | findstr "LISTENING" >nul
if errorlevel 1 (
  echo Spoustim GRAFIK Studio na portu 5174...
  rem npm --prefix install reads the repo root package.json, so install from inside studio\
  if not exist studio\node_modules (pushd studio & call npm install --no-audit --no-fund & popd)
  start "GRAFIK Studio" /min cmd /c "npm --prefix studio run dev"
) else (
  echo GRAFIK Studio uz bezi.
)

timeout /t 3 /nobreak >nul
start http://localhost:5174
