Add-Type -AssemblyName System.Windows.Forms
$hwnd = (Get-Process terminal64).MainWindowHandle
Write-Host "MT5 window handle: $hwnd"

# Use Win32 API to bring window to foreground
$code = @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
'@
$win32 = Add-Type -MemberDefinition $code -Name "Win32API" -Namespace Win32 -PassThru

# Restore if minimized
if ([Win32.Win32API]::IsIconic($hwnd)) {
    [Win32.Win32API]::ShowWindow($hwnd, 9)  # SW_RESTORE
    Start-Sleep -Milliseconds 500
}
[Win32.Win32API]::SetForegroundWindow($hwnd)
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait('^(e)')
Write-Host "Sent Ctrl+E"
