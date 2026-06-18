<#
.SYNOPSIS
    Uninstalls the AGENTX MT5 Bridge Windows Service.
#>

$ServiceName = "AgentXMT5Bridge"

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "Service '$ServiceName' is not installed."
    exit 0
}

Write-Host "Stopping service '$ServiceName'..."
nssm stop $ServiceName
Start-Sleep -Seconds 3

Write-Host "Removing service..."
nssm remove $ServiceName confirm
Start-Sleep -Seconds 2

Write-Host "✅ Service '$ServiceName' removed."
