@echo off
echo Stopping LinkedIn Agent 24/7 background service...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*daemon.js*' -or $_.CommandLine -like '*server.js*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('Killed PID ' + $_.ProcessId) }"
echo LinkedIn Agent stopped.
pause
