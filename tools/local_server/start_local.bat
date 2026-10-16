@echo off
rem Starts the Daily app + its scheduled jobs in the background (no window).
rem Open http://localhost:5050 in your browser. Logs: tools\local_server\server.log
cd /d "%~dp0\..\.."
if not exist dist\index.html call npx vite build
start "" pythonw tools\local_server\serve.py
echo Daily is starting in the background on http://localhost:5050
