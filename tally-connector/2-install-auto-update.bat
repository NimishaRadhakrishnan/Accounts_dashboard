@echo off
REM Runs the connector every 10 minutes while this computer is on. Run once.
cd /d "%~dp0"
schtasks /create /tn "Vishakan Tally Connector" /sc minute /mo 10 /tr "\"%~dp0run-connector.bat\"" /f
if %errorlevel%==0 (
  echo.
  echo Done. Figures will now go to the dashboard every 10 minutes.
  echo Sending the first full copy now. This can take a few minutes...
  py -3 vbt_tally_connector.py --full
) else (
  echo Could not create the scheduled task. Right-click this file and choose "Run as administrator".
)
pause
