@echo off
echo ============================================
echo  AGENTX - Enable MT5 Auto Trading
echo ============================================
echo.
echo This will try to find your MetaTrader 5 window
echo and enable the Algo Trading button.
echo.
echo STEP 1: Finding MT5 window...
echo.

:: Find and activate MT5 window
powershell -Command ^
  $hwnd = (Get-Process terminal64).MainWindowHandle; ^
  if ($hwnd -eq 0) { ^
    Write-Host 'MT5 not running. Starting it...'; ^
    Start-Process 'C:\Program Files\MetaTrader 5\terminal64.exe' -WindowStyle Normal; ^
    Start-Sleep 5; ^
    $hwnd = (Get-Process terminal64).MainWindowHandle; ^
  } ^
  Write-Host ('Window found: ' + $hwnd); ^
  $sig = @'^
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);^
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);^
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);^
  '@; ^
  $t = Add-Type -MemberDefinition $sig -Name WinAPI -Namespace Win32 -PassThru; ^
  if ([Win32.WinAPI]::IsIconic($hwnd)) { [Win32.WinAPI]::ShowWindow($hwnd, 9) }; ^
  [Win32.WinAPI]::SetForegroundWindow($hwnd); ^
  Write-Host 'Window activated - Click the ALGO TRADING button (green triangle)'; ^
  Write-Host 'Look at your MetaTrader 5 window. The green triangle button is'; ^
  Write-Host 'in the top toolbar. It turns green when AutoTrading is ON.';

echo.
echo ============================================
echo  NEXT STEP: In the MetaTrader 5 window that
echo  just appeared, click the ALGO TRADING button
echo  (green triangle icon on the top toolbar).
echo.
echo  OR use the keyboard: Press Ctrl+E
echo ============================================
echo.
pause
