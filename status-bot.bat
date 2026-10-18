@echo off
echo ==============================================
echo       LinkedIn Agent 24/7 Status Check
echo ==============================================
powershell -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*server.js*' }; if ($p) { Write-Host 'Status: ONLINE (PID ' $p.ProcessId ')' -ForegroundColor Green } else { Write-Host 'Status: OFFLINE' -ForegroundColor Red }"
echo.
echo Recent Bot Logs:
powershell -Command "if (Test-Path bot-server.log) { Get-Content bot-server.log -Tail 15 } else { Write-Host 'No log file found yet.' }"
echo ==============================================
pause
