@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0
python api\run_task.py --type incident
