@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  start "Windows Desktop Pet" pyw -3 main.py
) else (
  start "Windows Desktop Pet" pythonw main.py
)
endlocal

