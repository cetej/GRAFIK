@echo off
rem GRAFIK — jednoklikove spusteni.
rem   8300 = GRAFIK Engine v2 (obrazova sluzba pro vsechny projekty, lokalni FLUX)
rem   5174 = GRAFIK Studio v2 (React, /api -> 8300)
rem   Stary editor v1 je od 2026-10-23 pryc (git tag v1-final).
rem Bezici sluzby nespousti znovu (kontrola portu), takze je bezpecne pustit opakovane.
cd /d "%~dp0"
if not exist logs mkdir logs
rem Beh sluzby overuje curl: pod Command Center (bez konzole) netstat nic nevypise a findstr na roure z nej visel.

curl -s -o nul -m 3 http://127.0.0.1:8300/api/v2/health
if errorlevel 1 (
  echo Spoustim GRAFIK Engine na portu 8300...
  rem glTF Transform pro viewer.opt.glb (bez nej prohlizec nacita viewer.glb)
  if not exist engine\gltf\node_modules (pushd engine\gltf & call npm ci --no-audit --no-fund & popd)
  start "GRAFIK Engine" /min cmd /c "python -m uvicorn engine.app:app --port 8300 --host 127.0.0.1 --access-log >> logs\engine.log 2>&1"
) else (
  echo GRAFIK Engine uz bezi.
)

curl -s -o nul -m 3 http://127.0.0.1:5174/
if errorlevel 1 (
  echo Spoustim GRAFIK Studio na portu 5174...
  rem npm --prefix install reads the repo root package.json, so install from inside studio\
  if not exist studio\node_modules (pushd studio & call npm install --no-audit --no-fund & popd)
  start "GRAFIK Studio" /min cmd /c "npm --prefix studio run dev"
) else (
  echo GRAFIK Studio uz bezi.
)

rem timeout bez stdin selze, ping ceka i bez konzole
ping -n 4 127.0.0.1 >nul
start http://localhost:5174
