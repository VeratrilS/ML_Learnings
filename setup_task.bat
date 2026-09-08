@echo off
set "SCRIPT_PATH=%~dp0generate_and_send.py"
set "PYTHON_EXE=python.exe"

echo Registering daily background task for Incident Reporter...
set "RUN_SCRIPT=%~dp0run_task.bat"
schtasks /create /tn "Daily Incident Reporter" /tr "\"%RUN_SCRIPT%\"" /sc daily /st 14:00 /f
powershell -ExecutionPolicy Bypass -File "%~dp0update_task.ps1"

echo.
echo Task successfully scheduled! It will run natively in the background every day at 2:00 PM (14:00).
echo To remove this schedule later, open Task Scheduler or run:
echo schtasks /delete /tn "Daily Incident Reporter" /f
pause
