Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$hwnd = (Get-Process terminal64).MainWindowHandle
Write-Host "MT5 HWND: $hwnd"

# Use UI Automation to find the Algo Trading button
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::IsEnabledProperty, $true)

# Try to find the toggle button with "Algo Trading" tooltip
$algoCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, "Algo Trading")

$btn = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $algoCond)
if ($btn -ne $null) {
    Write-Host "Found Algo Trading button!"
    $invoke = $null
    $btn.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invoke)
    if ($invoke -ne $null) {
        $invoke.Invoke()
        Write-Host "Clicked Algo Trading button via UI Automation"
    } else {
        Write-Host "Button found but no InvokePattern"
    }
} else {
    Write-Host "Algo Trading button not found by name, trying alternatives..."
    # Try "Auto Trading"  
    $altCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, "Auto Trading")
    $btn2 = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $altCond)
    if ($btn2 -ne $null) {
        $invoke = $null
        $btn2.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invoke)
        if ($invoke -ne $null) {
            $invoke.Invoke()
            Write-Host "Clicked Auto Trading button"
        }
    } else {
        Write-Host "Neither Algo Trading nor Auto Trading button found"
    }
}

# List all buttons/toolbar items for debugging
$allBtns = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
Write-Host "Total UI elements: $($allBtns.Count)"
foreach ($el in $allBtns) {
    try {
        $name = $el.Current.Name
        if ($name -match "Trade|Algo|Auto|Expert|Bot|Strategy") {
            Write-Host "  Found: '$name' (CtrlType: $($el.Current.ControlType.ProgrammaticName))"
        }
    } catch {}
}
