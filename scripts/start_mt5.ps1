& $env:PSModulePath = $env:PSModulePath
$mt5 = "C:\Program Files\MetaTrader 5\terminal64.exe"
Write-Host "Starting MT5: $mt5"
$proc = Start-Process -FilePath $mt5 -WindowStyle Normal -PassThru
Write-Host "Started with PID: $($proc.Id)"
