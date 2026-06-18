<#
.SYNOPSIS
    Installs the AGENTX MT5 Bridge as a Windows Service using nssm.

.DESCRIPTION
    Downloads nssm if not found, then installs the bridge as a Windows Service
    that auto-starts on boot and restarts on failure.

.PARAMETER PythonPath
    Path to python.exe. Default: uses the same Python that runs this script.

.PARAMETER BridgePort
    Port for the bridge API. Default: 5000.

.PARAMETER NssmPath
    Path to nssm.exe. If not found, nssm is auto-downloaded to scripts/nssm.exe.

.EXAMPLE
    .\install_bridge_service.ps1
    .\install_bridge_service.ps1 -PythonPath "C:\Python312\python.exe" -BridgePort 5000
#>

param(
    [string]$PythonPath = "",
    [int]$BridgePort = 5000,
    [string]$NssmPath = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$ServiceName = "AgentXMT5Bridge"
$ServiceDisplayName = "AGENTX MT5 Bridge Service"

# ── Resolve python.exe ───────────────────────────────────────────────────────
if (-not $PythonPath) {
    $PythonPath = (Get-Command python).Source
}
if (-not $PythonPath -or -not (Test-Path $PythonPath)) {
    Write-Error "Python not found. Specify -PythonPath or ensure python is on PATH."
    exit 1
}
Write-Host "Using Python: $PythonPath"

# ── Resolve nssm.exe ─────────────────────────────────────────────────────────
if (-not $NssmPath) {
    $NssmPath = "$ScriptDir\nssm.exe"
}
if (-not (Test-Path $NssmPath)) {
    Write-Host "nssm.exe not found. Downloading..."
    $NssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
    $ZipPath = "$env:TEMP\nssm-2.24.zip"
    $ExtractPath = "$env:TEMP\nssm-extract"

    try {
        Invoke-WebRequest -Uri $NssmUrl -OutFile $ZipPath -UseBasicParsing
    } catch {
        Write-Error "Failed to download nssm. Install manually from https://nssm.cc/download"
        exit 1
    }

    Expand-Archive -Path $ZipPath -DestinationPath $ExtractPath -Force
    $nssmExe = Get-ChildItem -Path $ExtractPath -Recurse -Filter "nssm.exe" | Select-Object -First 1
    if (-not $nssmExe) {
        Write-Error "nssm.exe not found in extracted archive."
        exit 1
    }
    Copy-Item $nssmExe.FullName $NssmPath -Force
    Remove-Item $ExtractPath -Recurse -Force
    Write-Host "Downloaded nssm.exe to $NssmPath"
}

# ── Log directory ────────────────────────────────────────────────────────────
$LogDir = "$ProjectRoot\logs\bridge"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

# ── Check if service already exists ─────────────────────────────────────────
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Service '$ServiceName' already exists. Stopping and removing..."
    nssm stop $ServiceName
    Start-Sleep -Seconds 2
    nssm remove $ServiceName confirm
    Start-Sleep -Seconds 2
}

# ── Install service ─────────────────────────────────────────────────────────
$BridgeScript = "$ProjectRoot\bridge\__main__.py"
$AppParameters = "--port $BridgePort --log-level INFO"

Write-Host "Installing service '$ServiceName'..."
& $NssmPath install $ServiceName $PythonPath $BridgeScript

# Set service parameters
& $NssmPath set $ServiceName DisplayName $ServiceDisplayName
& $NssmPath set $ServiceName Description "AGENTX MT5 Bridge — REST + WebSocket API for MetaTrader 5"
& $NssmPath set $ServiceName AppParameters $AppParameters
& $NssmPath set $ServiceName AppDirectory $ProjectRoot
& $NssmPath set $ServiceName AppStdout "$LogDir\stdout.log"
& $NssmPath set $ServiceName AppStderr "$LogDir\stderr.log"
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateSeconds 86400
& $NssmPath set $ServiceName AppRotateBytes 10485760
& $NssmPath set $ServiceName AppExit Default Exit
& $NssmPath set $ServiceName Start SERVICE_AUTO_START
& $NssmPath set $ServiceName ObjectName "LocalSystem"

Write-Host "Starting service '$ServiceName'..."
& $NssmPath start $ServiceName

Start-Sleep -Seconds 3

# ── Verify ───────────────────────────────────────────────────────────────────
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host ""
    Write-Host "✅ AGENTX MT5 Bridge installed and running!"
    Write-Host "   Service: $ServiceName"
    Write-Host "   Port:    $BridgePort"
    Write-Host "   Logs:    $LogDir"
    Write-Host "   Test:    curl http://localhost:$BridgePort/health"
} else {
    Write-Warning "Service installed but may not be running. Check:"
    Write-Warning "   Get-Service $ServiceName"
    Write-Warning "   $LogDir\stderr.log"
}
