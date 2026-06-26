Set WshShell = CreateObject("WScript.Shell")
WScript.Sleep 500

' Find MT5 window and activate it
On Error Resume Next
WshShell.AppActivate "MetaQuotes"
If Err.Number <> 0 Then
    WshShell.AppActivate "MetaTrader"
End If
On Error Goto 0
WScript.Sleep 1000

' Send Ctrl+E to toggle Algo Trading
WshShell.SendKeys "^e"
WScript.Sleep 500
WshShell.SendKeys "^e"
WScript.Sleep 500
