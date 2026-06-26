Add-Type -AssemblyName System.Windows.Forms
$hwnd = (Get-Process terminal64).MainWindowHandle
Write-Host "MT5 HWND: $hwnd"

$code = @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
[DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hWnd, ref POINT lpPoint);
[DllImport("user32.dll")] public static extern IntPtr FindWindowEx(IntPtr hWndParent, IntPtr hWndChildAfter, string lpszClass, string lpszWindow);
[DllImport("user32.dll")] public static extern bool SendMessage(IntPtr hWnd, uint Msg, UIntPtr wParam, IntPtr lParam);

public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
public struct POINT { public int X; public int Y; }
'@
$win32 = Add-Type -MemberDefinition $code -Name "Win32API" -Namespace Win32 -PassThru

# Restore and activate window
if ([Win32.Win32API]::IsIconic($hwnd)) {
    [Win32.Win32API]::ShowWindow($hwnd, 9)
    Start-Sleep -Milliseconds 500
}
[Win32.Win32API]::SetForegroundWindow($hwnd)
Start-Sleep -Milliseconds 500

Write-Host "Foreground: $([Win32.Win32API]::GetForegroundWindow())"

# Get window rect
$rect = New-Object Win32API+RECT
[Win32.Win32API]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
$winX = $rect.Left
$winY = $rect.Top
$winW = $rect.Right - $rect.Left
Write-Host "Window: ($winX, $winY) - ($($rect.Right), $($rect.Bottom)), Width=$winW"

# The Algo Trading button is typically at the top-left of the toolbar
# Toolbar starts at (2, 2) relative to window, button size ~24x22
# Button 1: New chart (index 0), Button 2: Algo Trading (index 1)
# Actually, in MT5 build 5836+, the Algo Trading button is the FIRST button or SECOND
$btnX = $winX + 30  # Approximate - second button from left
$btnY = $winY + 30  # Top toolbar area

# Click approx position of the Algo Trading button
[System.Windows.Forms.Cursor]::Position = New-Object Drawing.Point($btnX, $btnY)
Start-Sleep -Milliseconds 200
Write-Host "Clicked at ($btnX, $btnY) - waiting..."
Start-Sleep -Milliseconds 2000

# Get cursor position back for verification
Write-Host "Cursor at: $([System.Windows.Forms.Cursor]::Position)"
