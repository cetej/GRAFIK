@echo off
rem GRAFIK — jednoklikove spusteni.
rem   8300 = GRAFIK Engine v2 (obrazova sluzba pro vsechny projekty, lokalni FLUX)
rem   8301 + 5173 = stary editor v1 (API + React UI), do konce G2 (rozhodnuti 2026-10-22, Q5)
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

netstat -ano | findstr ":8301 " | findstr "LISTENING" >nul
if errorlevel 1 (
  echo Spoustim stary GRAFIK API na portu 8301...
  start "GRAFIK API v1" /min cmd /c "python -m uvicorn grafik.api.app:app --port 8301 --host 127.0.0.1 --access-log >> logs\uvicorn-manual.log 2>&1"
) else (
  echo Stary GRAFIK API uz bezi.
)

netstat -ano | findstr ":5173 " | findstr "LISTENING" >nul
if errorlevel 1 (
  echo Spoustim stary GRAFIK editor na portu 5173...
  start "GRAFIK UI v1" /min cmd /c "set VITE_API_URL=http://localhost:8301&& npm --prefix ui-web run dev"
) else (
  echo GRAFIK UI uz bezi.
)

timeout /t 3 /nobreak >nul
start http://localhost:5173
