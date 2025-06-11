@echo off
echo 🧹 Terminating all Python-related processes...

taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM uvicorn.exe >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1

echo ✅ All Python processes terminated.
pause
