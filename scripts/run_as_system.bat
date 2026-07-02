schtasks /create /sc once /st 00:01 /tn "EnableRDP" /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Trading\scripts\enable_rdp.ps1" /ru SYSTEM /rl HIGHEST /f
schtasks /run /tn "EnableRDP"
ping -n 8 127.0.0.1 >nul
schtasks /delete /tn "EnableRDP" /f
