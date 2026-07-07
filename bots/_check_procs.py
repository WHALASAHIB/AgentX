#!/usr/bin/env python3
"""Check running python processes and identify bot script paths."""
import subprocess

# Use PowerShell to get process command lines
r = subprocess.run(
    ['powershell.exe', '-Command',
     'Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'" | '
     'Select-Object ProcessId, @{N="MB";E={[math]::Round($_.WorkingSetSize/1MB,1)}}, CommandLine | '
     'Format-List'],
    capture_output=True, text=True, timeout=15
)
print(r.stdout)
