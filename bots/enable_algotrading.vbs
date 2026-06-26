Set WshShell = CreateObject("WScript.Shell")

' Wait for terminal to be ready
WScript.Sleep 1000

' Activate MT5 window
On Error Resume Next
WshShell.AppActivate "FTMO-Demo"
If Err.Number <> 0 Then
    WshShell.AppActivate "MetaTrader 5"
End If
On Error Goto 0
WScript.Sleep 2000

' Send Ctrl+E to toggle Algo Trading (MT5 shortcut)
WshShell.SendKeys "^e"
WScript.Sleep 1000

' Send again to be sure
WshShell.SendKeys "^e"
WScript.Sleep 1000

' Also try Alt+T (Tools menu) then O (Options) then enable
' Actually, let's try a simpler approach: open Options dialog
WshShell.SendKeys "^o"
WScript.Sleep 2000

' Tab to Expert Advisors tab (tab key 4 times)
WshShell.SendKeys "{TAB 4}"
WScript.Sleep 500

' Space to check Allow Automated Trading
WshShell.SendKeys " "
WScript.Sleep 500

' Enter to close
WshShell.SendKeys "{ENTER}"
WScript.Sleep 1000
