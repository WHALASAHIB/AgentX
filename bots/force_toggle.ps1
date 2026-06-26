Add-Type -AssemblyName System.Windows.Forms
$hwnd = (Get-Process terminal64).MainWindowHandle
Write-Host "MT5 HWND: $hwnd"

$code = @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
'@
$win32 = Add-Type -MemberDefinition $code -Name "Win32API" -Namespace Win32 -PassThru

if ([Win32.Win32API]::IsIconic($hwnd)) {
    [Win32.Win32API]::ShowWindow($hwnd, 9)
    Start-Sleep -Milliseconds 1000
}

$result = [Win32.Win32API]::SetForegroundWindow($hwnd)
Write-Host "SetForegroundWindow: $result"
Start-Sleep -Milliseconds 500

$fg = [Win32.Win32API]::GetForegroundWindow()
Write-Host "Foreground window after activation: $fg"
Write-Host "Target: $hwnd"
if ($fg -eq $hwnd) {
    Write-Host "Window IS foreground, sending Ctrl+E now..."
    [System.Windows.Forms.SendKeys]::SendWait('^(e)')
    Write-Host "Ctrl+E sent"
    Start-Sleep -Milliseconds 1000
    # Send it again for good measure
    [System.Windows.Forms.SendKeys]::SendWait('^(e)')
    Write-Host "Ctrl+E sent again"
} else {
    Write-Host "Window not foreground, trying Alt+Space then..."
    # Try activating via Alt
    [System.Windows.Forms.SendKeys]::SendWait('%')
}
