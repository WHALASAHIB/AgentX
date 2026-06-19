$path = "C:\WINDOWS\system32\config\systemprofile\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\config"
if (!(Test-Path $path)) { New-Item -ItemType Directory -Path $path -Force }
$ini = Join-Path $path "terminal.ini"
$content = "[ExpertAdvisors]`r`nAutoTrading=1`r`n"
[System.IO.File]::WriteAllText($ini, $content, [System.Text.Encoding]::Unicode)
Write-Host "Written: $ini"
Get-Content $ini
