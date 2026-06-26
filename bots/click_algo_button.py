import ctypes
from ctypes import wintypes
import time
import sys
import os

user32 = ctypes.windll.user32

# Define FindWindowExW
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND

# Find MT5 window
hwnd = user32.FindWindowW("MetaTrader", None)
if not hwnd:
    # Enumerate all windows
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    found = [None]
    def enum_cb(h, lp):
        length = user32.GetWindowTextLengthW(h)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(h, buff, length + 1)
            if "MetaTrader" in buff.value or "MetaQuotes" in buff.value:
                found[0] = h
                return False
        return True
    EnumWindows = user32.EnumWindows
    EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_int]
    EnumWindows(WNDENUMPROC(enum_cb), 0)
    hwnd = found[0]

if not hwnd:
    print("No MT5 window found")
    sys.exit(1)

print(f"MT5 window: {hwnd:#x}")

# Bring to foreground
user32.ShowWindow(hwnd, 1)  # SW_SHOWNORMAL
time.sleep(0.3)
user32.SetForegroundWindow(hwnd)
time.sleep(0.5)

# Get rect
rect = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
w = rect.right - rect.left
h = rect.bottom - rect.top
print(f"Window: {w}x{h} at ({rect.left},{rect.top})")

# Find toolbar
toolbar = user32.FindWindowExW(hwnd, None, "ToolbarWindow32", None)
print(f"Toolbar: {toolbar:#x}")

if toolbar:
    # Get toolbar position
    tb_rect = wintypes.RECT()
    user32.GetWindowRect(toolbar, ctypes.byref(tb_rect))
    print(f"Toolbar: ({tb_rect.left},{tb_rect.top}) - ({tb_rect.right},{tb_rect.bottom})")
    
    # Button 1 in toolbar (Algo Trading) - count 32px from left
    btn_count = user32.SendMessageW(toolbar, 0x418, 0, 0)  # TB_BUTTONCOUNT
    print(f"Toolbar buttons: {btn_count}")
    
    # Try to get button rects
    for i in range(min(btn_count or 8, 8)):
        btn_rect = wintypes.RECT()
        # TB_GETITEMRECT = 0x41D
        ptr = ctypes.addressof(btn_rect)
        res = user32.SendMessageW(toolbar, 0x41D, i, ptr)
        if res:
            print(f"  Btn {i}: ({btn_rect.left},{btn_rect.top})-({btn_rect.right},{btn_rect.bottom})")
    
    # Click approximate position of Algo Trading button (button index 1)
    if btn_count > 1:
        btn_rect = wintypes.RECT()
        ptr = ctypes.addressof(btn_rect)
        res = user32.SendMessageW(toolbar, 0x41D, 1, ptr)
        if res:
            cx = (btn_rect.left + btn_rect.right) // 2
            cy = (btn_rect.top + btn_rect.bottom) // 2
            # Convert toolbar-relative to screen
            screen_x = tb_rect.left + cx
            screen_y = tb_rect.top + cy
        else:
            screen_x = tb_rect.left + 30  # default offset
            screen_y = tb_rect.top + 12
    else:
        screen_x = tb_rect.left + 30
        screen_y = tb_rect.top + 12
    
    print(f"Clicking at ({screen_x}, {screen_y})")
    user32.SetCursorPos(screen_x, screen_y)
    time.sleep(0.2)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
    time.sleep(0.5)
    print("Clicked button 1")

# Also try sending Ctrl+E using keybd_event properly
VK_CONTROL = 0x11
VK_E = 0x45
KEYEVENTF_EXTENDEDKEY = 0x0001

user32.keybd_event(VK_CONTROL, 0, 0, 0)
time.sleep(0.1)
user32.keybd_event(VK_E, 0, 0, 0)
time.sleep(0.05)
user32.keybd_event(VK_E, 0, 2, 0)  # KEYEVENTF_KEYUP
time.sleep(0.1)
user32.keybd_event(VK_CONTROL, 0, 2, 0)
print("Ctrl+E sent")

# Wait and test
time.sleep(2)

# Test AutoTrading state
sys.path.insert(0, os.path.abspath("C:\\Trading"))
import MetaTrader5 as mt5
if mt5.initialize():
    ti = mt5.terminal_info()
    print(f"Terminal trade_allowed: {ti.trade_allowed}")
    mt5.shutdown()
