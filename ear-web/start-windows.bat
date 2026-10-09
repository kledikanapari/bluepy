@echo off
rem Starts the local ear (web) server and opens it in the browser.
rem Close this window to stop the server (not needed once the app is installed).
cd /d "%~dp0"
where node >nul 2>nul || (echo Node.js is not installed: download it from https://nodejs.org/ & pause & exit /b 1)
start "" http://localhost:8080/
node server.js
pause
