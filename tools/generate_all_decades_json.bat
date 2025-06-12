@echo off
setlocal enabledelayedexpansion

:: Set the FastAPI base URL
set BASE_URL=http://127.0.0.1:8000/generate-json

:: Set genre and language
set GENRE=jazz
set LANGUAGE=English
set NUM_TRACKS=40

:: Get timestamp for log file
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set LOGFILE=track_log_%%i.txt

echo 🚀 Starting batch generation... > %LOGFILE%
echo Genre: %GENRE%, Language: %LANGUAGE%, Tracks per Decade: %NUM_TRACKS% >> %LOGFILE%
echo. >> %LOGFILE%

:: Loop through decades
for %%D in (1950s 1960s 1970s 1980s 1990s 2000s 2010s 2020s) do (
    echo ------------------------------------------------------
    echo 🕒 Sending request for %%D - %GENRE%
    echo 🕒 %%D >> %LOGFILE%
    curl -s -X POST %BASE_URL% ^
        -H "Content-Type: application/json" ^
        -d "{\"decade\": \"%%D\", \"genre\": \"%GENRE%\", \"language\": \"%LANGUAGE%\", \"num_tracks\": %NUM_TRACKS%}" >> %LOGFILE%
    echo. >> %LOGFILE%
    echo Done with %%D.
    timeout /t 1 > nul
)

:: ✅ Notify user
echo ✅ All requests sent. Log saved to %LOGFILE%
echo 🔔 Done! Playing notification sound...
powershell -c (New-Object Media.SoundPlayer "C:\Windows\Media\notify.wav").PlaySync();

pause
