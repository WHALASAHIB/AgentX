Add-Type -AssemblyName System.Windows.Forms
$hwnd = (Get-Process terminal64).MainWindowHandle
Write-Host "MT5 HWND: $hwnd"
Write-Host "Title: $((Get-Process terminal64).MainWindowTitle)"

$code = @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern bool AllowSetForegroundWindow(int pid);
'@
$win32 = Add-Type -MemberDefinition $code -Name "Win32API" -Namespace Win32 -PassThru

# Allow our process to set foreground
[Win32.Win32API]::AllowSetForegroundWindow((Get-Process terminal64).Id) | Out-Null
Start-Sleep -Milliseconds 200

if ([Win32.Win32API]::IsIconic($hwnd)) {
    [Win32.Win32API]::ShowWindow($hwnd, 9)
    Start-Sleep -Milliseconds 500
}
[Win32.Win32API]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 500

$fg = [Win32.Win32API]::GetForegroundWindow()
Write-Host "Foreground: $fg (target: $hwnd)"
if ($fg -eq $hwnd) {
    Write-Host "Window is foreground, sending Ctrl+E..."
    [System.Windows.Forms.SendKeys]::SendWait('^(e)')
    Write-Host "Ctrl+E sent"
    Start-Sleep -Milliseconds 1000
    [System.Windows.Forms.SendKeys]::SendWait('^(e)')
    Write-Host "Ctrl+E sent again"
} else {
    Write-Host "Window NOT foreground, retrying..."
    [Win32.Win32API]::ShowWindow($hwnd, 1)  # SW_SHOWNORMAL
    Start-Sleep -Milliseconds 500
    [Win32.Win32API]::SetForegroundWindow($hwnd)
    Start-Sleep -Milliseconds 1000
    Write-Host "Foreground now: $([Win32.Win32API]::GetForegroundWindow())"
    [System.Windows.Forms.SendKeys]::SendWait('^(e)')
    Write-Host "Ctrl+E sent via retry"
}

# Wait and test
Start-Sleep -Seconds 3
