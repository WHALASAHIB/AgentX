Add-Type -AssemblyName System.Windows.Forms
$hwnd = (Get-Process terminal64).MainWindowHandle
Write-Host "HWND: $hwnd"

$code = @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
'@
$win32 = Add-Type -MemberDefinition $code -Name "Win32API" -Namespace Win32 -PassThru
if ([Win32.Win32API]::IsIconic($hwnd)) {
    [Win32.Win32API]::ShowWindow($hwnd, 9)
    Start-Sleep -Milliseconds 500
}
[Win32.Win32API]::SetForegroundWindow($hwnd)
Start-Sleep -Milliseconds 1000
# Try Alt+T (MT5 shortcut for Algo Trading)
[System.Windows.Forms.SendKeys]::SendWait('%t')
Write-Host "Sent Alt+T"
Start-Sleep -Seconds 2
