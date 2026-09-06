# -*- coding: utf-8 -*-
import sys
import time
import os
import ctypes
from ctypes import wintypes

from pywinauto import Desktop, Application
from PIL import ImageGrab

path = sys.argv[1]
shot = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\MACAU\Desktop\天池\work\inspect_usd\screen_upload.png"
assert os.path.isfile(path), path
print("ZIP", path, os.path.getsize(path))

hwnd = 0x40a42
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GetWindowText = user32.GetWindowTextW
GetWindowTextLength = user32.GetWindowTextLengthW
IsWindowVisible = user32.IsWindowVisible
GetClassName = user32.GetClassNameW
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def get_text(h):
    n = GetWindowTextLength(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    GetWindowText(h, buf, n + 1)
    return buf.value


def get_class(h):
    buf = ctypes.create_unicode_buffer(256)
    GetClassName(h, buf, 256)
    return buf.value


def foreground_chrome():
    fg = user32.GetForegroundWindow()
    our = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    user32.AttachThreadInput(fg_tid, our, True)
    user32.ShowWindow(hwnd, 3)
    user32.SetForegroundWindow(hwnd)
    user32.AttachThreadInput(fg_tid, our, False)
    time.sleep(0.4)


def find_open_dialogs():
    hits = []

    def cb(h, lparam):
        if IsWindowVisible(h) and get_class(h) == "#32770":
            t = get_text(h)
            if t in ("打开", "Open", "打开文件"):
                hits.append(h)
        return True

    EnumWindows(EnumWindowsProc(cb), 0)
    return hits


foreground_chrome()
w = Desktop(backend="uia").window(handle=hwnd)
btn = w.child_window(title="提交结果", control_type="Button")
print("BTN", btn.rectangle(), "enabled", btn.is_enabled())
btn.click_input()
print("CLICKED_SUBMIT")

dlg_h = None
for i in range(20):
    time.sleep(0.4)
    hits = find_open_dialogs()
    if hits:
        dlg_h = hits[0]
        print("DIALOG", hex(dlg_h), get_text(dlg_h))
        break
if dlg_h is None:
    ImageGrab.grab().save(shot)
    raise SystemExit("NO_FILE_DIALOG")

app = Application(backend="win32").connect(handle=dlg_h)
dlg = app.window(handle=dlg_h)
dlg.set_focus()
time.sleep(0.2)

filename_edit = None
for c in dlg.descendants():
    if c.friendly_class_name() != "Edit":
        continue
    r = c.rectangle()
    print("EDIT", r, repr(c.window_text())[:80])
    # filename box sits on the bottom row, right of 文件名
    if r.top > 400 and r.left > 150 and r.width() > 200:
        filename_edit = c

if filename_edit is None:
    ImageGrab.grab().save(shot)
    raise SystemExit("NO_FILENAME_EDIT")

filename_edit.set_edit_text(path)
print("SET", filename_edit.window_text())
time.sleep(0.3)

open_btn = None
for c in dlg.descendants():
    t = c.window_text() or ""
    if "打开" in t and c.friendly_class_name() == "Button":
        print("OPEN_CAND", t, c.rectangle())
        open_btn = c
        break
if open_btn is None:
    ImageGrab.grab().save(shot)
    raise SystemExit("NO_OPEN_BUTTON")
open_btn.click()
print("CLICKED_OPEN")
time.sleep(2.0)
ImageGrab.grab().save(shot)
print("SAVED", shot)
