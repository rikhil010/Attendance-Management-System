@echo off
REM Start GWASOAT Application
cd /d "c:\Users\rikhi\OneDrive\Documents\PlatformIO\Projects\GWASOAT"
echo Starting GWASOAT Application...
echo.
echo If the app starts successfully, you will see:
echo - "Running on http://127.0.0.1:5000"
echo.
python python/src/app.py
pause
