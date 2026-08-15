@echo off
rem GRAFIK — jednoklikove spusteni API (8300) + UI (5173) + otevreni prohlizece.
rem Bezici sluzby nespousti znovu (kontrola portu), takze je bezpecne pustit opakovane.
cd /d "%~dp0"
if not exist logs mkdir logs

netstat -ano | findstr ":8300" | findstr "LISTENING" >nul
if errorlevel 1 (
  echo Spoustim GRAFIK API na portu 8300...
  start "GRAFIK API" /min cmd /c "python -m uvicorn grafik.api.app:app --port 8300 --host 127.0.0.1 --access-log >> logs\uvicorn-manual.log 2>&1"
) else (
  echo GRAFIK API uz bezi.
)

netstat -ano | findstr ":5173" | findstr "LISTENING" >nul
if errorlevel 1 (
  echo Spoustim GRAFIK UI na portu 5173...
  start "GRAFIK UI" /min cmd /c "npm --prefix ui-web run dev"
) else (
  echo GRAFIK UI uz bezi.
)

timeout /t 3 /nobreak >nul
start http://localhost:5173
