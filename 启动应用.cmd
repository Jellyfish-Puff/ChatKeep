@echo off
cd /d "%~dp0"
if exist "%~dp0dist\ChatKeep.exe" (
  start "" "%~dp0dist\ChatKeep.exe"
  exit /b
)
start "" "%~dp0src\ChatArchive\bin\Release\net10.0-windows\ChatKeep.exe"
