@echo off
rem Daily apply run, for Windows Task Scheduler (see README "Run it every day"). Unattended: fills and submits complete
rem forms on Greenhouse / Lever / Ashby / SmartRecruiters (and Workday once Sai has the account), reads security codes
rem from Gmail, lists everything else for Sai. Log: tools\apply_assist\runs\daily.log
cd /d "%~dp0\..\.."
set PYTHONUNBUFFERED=1
if not exist tools\apply_assist\runs mkdir tools\apply_assist\runs
echo ===== %date% %time% ===== >> tools\apply_assist\runs\daily.log
"C:\Users\saira\anaconda3\python.exe" tools\apply_assist\assist.py --auto --submit --no-harvest --ask-timeout 1 --handoff-wait 1 --max 30 >> tools\apply_assist\runs\daily.log 2>&1
