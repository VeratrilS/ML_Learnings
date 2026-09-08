@echo off
set "RUN_SCRIPT=%~dp0run_leetcode.bat"
echo Registering hourly background task for LeetCode Notifier...
schtasks /create /tn "Hourly LeetCode Notifier" /tr "\"%RUN_SCRIPT%\"" /sc hourly /f
echo Task successfully scheduled!
pause
