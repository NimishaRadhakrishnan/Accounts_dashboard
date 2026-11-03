@echo off
schtasks /delete /tn "Vishakan Tally Connector" /f
echo The connector will no longer run automatically.
pause
