"""Mouse and keyboard through Win32 SendInput.

SendInput marks every event as injected (LLMHF_INJECTED), which is how the
shell's low-level mouse hook tells the automation's moves apart from the
user's: a real hand on the mouse for 1 s pauses the run (see shell/src/guard.rs).

Coordinates are physical pixels of the primary monitor; the process is made
per-monitor DPI aware so they match the screenshot's pixels.
"""
import ctypes
import math
import random
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE = 0x0001, 0x8000
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _mouse(flags, dx=0, dy=0, data=0):
    return INPUT(INPUT_MOUSE, _U(mi=MOUSEINPUT(dx, dy, data, flags, 0, 0)))


def _key(vk=0, scan=0, flags=0):
    return INPUT(INPUT_KEYBOARD, _U(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))


def screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def cursor_pos():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def _move_to(x, y):
    w, h = screen_size()
    _send(_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                 round(x * 65535 / (w - 1)), round(y * 65535 / (h - 1))))


class Cancelled(Exception):
    """The run was paused/stopped while the cursor was travelling."""


def glide(x, y, should_stop=lambda: False):
    """Moves the cursor to (x, y) along a gentle arc with ease-in-out, so the
    user can follow where it is going. Aborts (raising Cancelled) as soon as
    should_stop() says the run was paused, leaving the cursor to the user."""
    x0, y0 = cursor_pos()
    dist = math.hypot(x - x0, y - y0)
    if dist < 2:
        return
    duration = min(0.9, 0.25 + dist / 2500)
    # Control point off the straight line -> a slight curve, like a hand.
    bend = random.uniform(-0.18, 0.18) * dist
    mx, my = (x0 + x) / 2, (y0 + y) / 2
    nx, ny = -(y - y0) / dist, (x - x0) / dist
    cx, cy = mx + nx * bend, my + ny * bend
    start = time.perf_counter()
    while True:
        if should_stop():
            raise Cancelled()
        t = min(1.0, (time.perf_counter() - start) / duration)
        e = 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2  # easeInOutCubic
        px = (1 - e) ** 2 * x0 + 2 * (1 - e) * e * cx + e ** 2 * x
        py = (1 - e) ** 2 * y0 + 2 * (1 - e) * e * cy + e ** 2 * y
        _move_to(px, py)
        if t >= 1.0:
            return
        time.sleep(1 / 120)


def click(button="left", double=False):
    down, up = ((MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP) if button == "left"
                else (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP))
    for _ in range(2 if double else 1):
        _send(_mouse(down))
        time.sleep(0.03)
        _send(_mouse(up))
        time.sleep(0.06)


def scroll(direction, notches=5):
    amount = 120 * notches * (1 if direction == "up" else -1)
    _send(_mouse(MOUSEEVENTF_WHEEL, data=ctypes.c_uint32(amount).value))


def type_text(text):
    for ch in text:
        if ch == "\n":
            press("enter")
            continue
        for unit in _utf16(ch):
            _send(_key(scan=unit, flags=KEYEVENTF_UNICODE),
                  _key(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
        time.sleep(0.008)


def _utf16(ch):
    b = ch.encode("utf-16-le")
    return [int.from_bytes(b[i:i + 2], "little") for i in range(0, len(b), 2)]


VK = {
    "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "backspace": 0x08, "delete": 0x2E,
    "space": 0x20, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "home": 0x24,
    "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "ctrl": 0x11, "control": 0x11,
    "shift": 0x10, "alt": 0x12, "win": 0x5B,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}


def press(combo):
    """Presses a key or combination like "enter", "ctrl+l", "alt+tab"."""
    names = [k.strip().lower() for k in combo.split("+") if k.strip()]
    vks = []
    for n in names:
        if n in VK:
            vks.append(VK[n])
        elif len(n) == 1:
            vks.append(user32.VkKeyScanW(ord(n)) & 0xFF)
        else:
            raise ValueError(f"tecla desconhecida: {n}")
    _send(*[_key(vk=v) for v in vks])
    time.sleep(0.03)
    _send(*[_key(vk=v, flags=KEYEVENTF_KEYUP) for v in reversed(vks)])


# --- windows -------------------------------------------------------------

def window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def window_rect_at(x, y):
    """Rect of the top-level window under a screen point."""
    hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
    return window_rect(user32.GetAncestor(hwnd, 2) or hwnd)  # GA_ROOT


def find_window(title, exact=False):
    """First visible top-level window whose title contains (or, with exact,
    equals) `title`."""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        name = window_title(hwnd).lower()
        if user32.IsWindowVisible(hwnd) and (name == title.lower() if exact else title.lower() in name):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def foreground_title():
    return window_title(user32.GetForegroundWindow())


def point_in(rect, x, y):
    return rect[0] <= x < rect[2] and rect[1] <= y < rect[3]
