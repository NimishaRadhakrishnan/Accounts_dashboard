@echo off
cd /d "%~dp0"
echo Checking the connection to Tally and to the dashboard...
echo.
py -3 vbt_tally_connector.py --test
echo.
pause
