from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import time


user32 = ctypes.windll.user32
SWP_NOACTIVATE = 0x0010
SWP_NOZORDER = 0x0004
GA_ROOT = 2


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


@dataclass(frozen=True)
class WorkArea:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self): return self.right - self.left

    @property
    def height(self): return self.bottom - self.top

    @property
    def center_x(self): return (self.left + self.right) // 2


def monitor_work_areas() -> list[WorkArea]:
    found: list[WorkArea] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR,
                                      wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM)

    def callback(monitor, _dc, _rect, _data):
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            r = info.rcWork
            found.append(WorkArea(r.left, r.top, r.right, r.bottom))
        return True

    cb = callback_type(callback)
    user32.EnumDisplayMonitors(None, None, cb, 0)
    return found


def cursor_position() -> tuple[int, int]:
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def set_window_position(hwnd: int, x: int, y: int, width: int, height: int) -> None:
    """Move using absolute virtual-desktop coordinates, including negative values."""
    top_level = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
    user32.SetWindowPos(top_level, None, int(x), int(y), int(width), int(height),
                        SWP_NOACTIVATE | SWP_NOZORDER)


def area_at(x: int, y: int, areas: list[WorkArea]) -> WorkArea | None:
    return next((a for a in areas if a.left <= x < a.right and a.top <= y < a.bottom), None)


def clamp_to_area(x: int, y: int, width: int, height: int, area: WorkArea) -> tuple[int, int]:
    return (min(max(int(x), area.left), area.right - width),
            min(max(int(y), area.top), area.bottom - height))


def external_edges(areas: list[WorkArea]) -> list[tuple[WorkArea, str]]:
    """Edges not shared with another monitor; internal dual-screen seams are excluded."""
    result = []
    for area in areas:
        vertical_overlap = lambda other: min(area.bottom, other.bottom) > max(area.top, other.top)
        horizontal_overlap = lambda other: min(area.right, other.right) > max(area.left, other.left)
        if not any(other != area and other.right == area.left and vertical_overlap(other) for other in areas):
            result.append((area, "left"))
        if not any(other != area and other.left == area.right and vertical_overlap(other) for other in areas):
            result.append((area, "right"))
        if not any(other != area and other.bottom == area.top and horizontal_overlap(other) for other in areas):
            result.append((area, "top"))
    return result


class ActivityPoller:
    """Detects activity type; never translates or stores keys or typed text."""

    MOUSE_BUTTONS = (0x01, 0x02, 0x04)

    def __init__(self):
        self.last_cursor = cursor_position()
        self.last_activity = time.monotonic()
        self._key_down = [False] * 256

    def poll(self) -> set[str]:
        events: set[str] = set()
        current_cursor = cursor_position()
        if current_cursor != self.last_cursor:
            events.add("mouse")
            self.last_cursor = current_cursor

        for vk in range(1, 256):
            down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            if down and not self._key_down[vk]:
                events.add("click" if vk in self.MOUSE_BUTTONS else "typing")
            self._key_down[vk] = down

        if events:
            self.last_activity = time.monotonic()
        return events


def nearest_area(x: int, y: int, areas: list[WorkArea]) -> WorkArea:
    containing = [a for a in areas if a.left <= x < a.right and a.top <= y < a.bottom]
    if containing:
        return containing[0]
    return min(areas, key=lambda a: abs(a.center_x - x) + abs((a.top + a.bottom) // 2 - y))
