@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0
python backend\run_task.py --type leetcode
