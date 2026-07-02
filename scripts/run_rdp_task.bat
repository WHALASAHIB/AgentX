schtasks /create /sc onlogon /tn "AgentX_EnableRDP" /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Trading\scripts\enable_rdp.ps1" /f
schtasks /run /tn "AgentX_EnableRDP"
ping -n 12 127.0.0.1 >nul
schtasks /delete /tn "AgentX_EnableRDP" /f
