@echo off
title Enabling Remote Desktop...
echo ============================================
echo  Enabling Remote Desktop for MacBook Access
echo ============================================
echo.
echo Step 1: Enabling RDP...
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f
echo.
echo Step 2: Opening firewall...
netsh advfirewall firewall set rule group="remote desktop" new enable=Yes
echo.
echo Step 3: Restarting Terminal Services...
net stop TermService /y
net start TermService
echo.
echo ============================================
echo  ✅ Remote Desktop Enabled!
echo ============================================
echo.
echo Connection Details:
echo   Computer: %COMPUTERNAME%
echo   IP: 10.10.10.100
echo   User: Trading X Agents
echo.
echo On your MacBook:
echo   1. Install "Microsoft Remote Desktop" from App Store
echo   2. Add PC: 10.10.10.100 or %COMPUTERNAME%
echo   3. Login with: Trading X Agents + your password
echo.
pause
