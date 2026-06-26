Add-Type -AssemblyName System.Windows.Forms
$hwnd = (Get-Process terminal64).MainWindowHandle
Write-Host "MT5 HWND: $hwnd"

$code = @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool AllowSetForegroundWindow(int pid);
'@
$win32 = Add-Type -MemberDefinition $code -Name "Win32API" -Namespace Win32 -PassThru

# Allow our process to set foreground
[Win32.Win32API]::AllowSetForegroundWindow((Get-Process terminal64).Id) | Out-Null

if ([Win32.Win32API]::IsIconic($hwnd)) {
    [Win32.Win32API]::ShowWindow($hwnd, 9)
    Start-Sleep -Milliseconds 500
}
[Win32.Win32API]::BringWindowToTop($hwnd) | Out-Null
Start-Sleep -Milliseconds 200
[Win32.Win32API]::SetForegroundWindow($hwnd) | Out-Null
Write-Host "Activated"
Start-Sleep -Milliseconds 1000

# Open Options dialog with Ctrl+O
[System.Windows.Forms.SendKeys]::SendWait('^(o)')
Write-Host "Sent Ctrl+O (Options)"
Start-Sleep -Milliseconds 1500

# Now in Options dialog. Send Alt+E to go to Expert Advisors tab
[System.Windows.Forms.SendKeys]::SendWait('%e')
Write-Host "Sent Alt+E (Expert Advisors tab)"
Start-Sleep -Milliseconds 500

# Tab to the checkbox and press Space to check it
[System.Windows.Forms.SendKeys]::SendWait('{TAB 3}')
Start-Sleep -Milliseconds 300

# Hit Enter to check it
[System.Windows.Forms.SendKeys]::SendWait(' ')
Write-Host "Sent Space to check Allow"
Start-Sleep -Milliseconds 300

# Hit Enter to close Options
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Write-Host "Sent Enter to close Options"
Start-Sleep -Milliseconds 1000
