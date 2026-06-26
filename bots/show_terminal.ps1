$pid = 11584
$hwnd = (Get-Process -Id $pid).MainWindowHandle
Write-Host "PID: $pid, HWND: $hwnd"

if ($hwnd -eq 0) {
    Write-Host "No window handle (headless). Trying to create window..."
    
    $code = @'
[DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
'@
    $type = Add-Type -MemberDefinition $code -Name "Win32API2" -Namespace Win32 -PassThru
    
    # Get process handle
    $process = Get-Process -Id $pid
    $hwnd = $process.MainWindowHandle
    Write-Host "After getting process: HWND = $hwnd"
    
    if ($hwnd -eq 0) {
        # Try to get the first window of the process
        $EnumWindows = @'
[DllImport("user32.dll")] public static extern bool EnumWindows(System.Delegate lpEnumFunc, int lParam);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
'@
        $enumType = Add-Type -MemberDefinition $EnumWindows -Name "Win32API3" -Namespace Win32 -PassThru
        
        $targetPid = $pid
        $foundHwnd = [IntPtr]::Zero
        $callback = {
            param($hWnd, $lParam)
            $outPid = 0
            [Win32.Win32API3]::GetWindowThreadProcessId($hWnd, [ref]$outPid)
            if ($outPid -eq $targetPid) {
                $script:foundHwnd = $hWnd
                return $false
            }
            return $true
        }
        $enumDelegate = [System.Delegate]::CreateDelegate([System.Func[IntPtr, IntPtr, bool]], $null, $callback.Method)
        
        write-host "Enumerating windows for PID $targetPid..."
        
        # Actually, this approach is too complex. Let me try a simpler method.
    }
} else {
    Write-Host "Window exists. Trying to show it."
    [Win32.Win32API2]::ShowWindowAsync($hwnd, 5) | Out-Null
    [Win32.Win32API2]::SetWindowPos($hwnd, -1, 100, 100, 1280, 720, 0x0040) | Out-Null
}
