# Enable RDP without elevation check
$ts = Get-WmiObject -Namespace "root/cimv2/terminalservices" -Class "Win32_TerminalServiceSetting" -EnableAllPrivileges -ErrorAction Stop
$result = $ts.SetAllowTSConnections(1, 1)
Write-Host "WMI result: $($result.ReturnValue)"
Write-Host "RDP enabled via WMI"
