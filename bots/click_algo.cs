// Compile on Windows: csc /target:winexe /reference:System.Windows.Forms.dll click_algo.cs
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Windows.Forms;

class ClickAlgo
{
    [DllImport("user32.dll")]
    static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    static extern bool IsIconic(IntPtr hWnd);

    [DllImport("user32.dll", SetLastError = true)]
    static extern bool SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", SetLastError = true)]
    static extern IntPtr FindWindow(string lpClassName, string lpWindowName);

    [DllImport("user32.dll")]
    static extern IntPtr FindWindowEx(IntPtr hWndParent, IntPtr hWndChildAfter,
        string lpszClass, string lpszWindow);

    // WM_COMMAND: Common MT5 toolbar IDs for Algo Trading toggle
    // Build 5836 Algo Trading button command ID
    const int CMD_ALGO_TRADING = 32791;
    const uint WM_COMMAND = 0x0111;

    static void Main()
    {
        Process[] procs = Process.GetProcessesByName("terminal64");
        if (procs.Length == 0)
        {
            Console.WriteLine("MT5 not running");
            return;
        }

        IntPtr hWnd = procs[0].MainWindowHandle;
        Console.WriteLine($"MT5 HWND: {hWnd}");

        if (hWnd == IntPtr.Zero)
        {
            Console.WriteLine("No main window handle (headless mode)");
            Console.WriteLine("Trying direct command anyway...");

            // Try sending WM_COMMAND directly to the process
            // The Algo Trading button might respond to command ID
            foreach (var proc in procs)
            {
                IntPtr handle = proc.Handle;
                // Can't send WM_COMMAND without a window handle
            }
            Console.WriteLine("Cannot interact with headless terminal.");
            Console.WriteLine("Please start MetaTrader 5 manually via the Start Menu or Desktop shortcut,");
            Console.WriteLine("log into your account, and click the green 'Algo Trading' button.");
            return;
        }

        // Restore window
        if (IsIconic(hWnd))
            ShowWindow(hWnd, 9); // SW_RESTORE
        SetForegroundWindow(hWnd);

        // Send WM_COMMAND with Algo Trading toggle ID
        SendMessage(hWnd, WM_COMMAND, (IntPtr)CMD_ALGO_TRADING, IntPtr.Zero);
        Console.WriteLine($"Sent WM_COMMAND {CMD_ALGO_TRADING} (Algo Trading toggle)");

        // Try alternative IDs
        int[] altIds = { 40971, 32807, 33065, 57601, 57602, 57603, 32789, 32790 };
        foreach (int id in altIds)
        {
            SendMessage(hWnd, WM_COMMAND, (IntPtr)id, IntPtr.Zero);
            Console.WriteLine($"Also tried: {id}");
        }
    }
}
