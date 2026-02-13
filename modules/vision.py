# vision.py
# Fast, low-cost “observation” utilities for your desktop agent.
# Key ideas:
# - Prefer text/UI state over screenshots
# - If you must screenshot, capture ACTIVE WINDOW, return BYTES (no disk)

import io
import os
import time
from typing import Optional, Dict, Any

import mss
from PIL import Image

try:
    import pygetwindow as gw
except Exception:
    gw = None


def get_active_window_info() -> Dict[str, Any]:
    """
    Returns lightweight state you can feed to the LLM instead of a screenshot.
    """
    info: Dict[str, Any] = {"title": "", "left": None, "top": None, "width": None, "height": None}
    if gw is None:
        return info

    try:
        w = gw.getActiveWindow()
        if not w:
            return info
        info.update(
            {
                "title": w.title or "",
                "left": int(w.left),
                "top": int(w.top),
                "width": int(w.width),
                "height": int(w.height),
            }
        )
        return info
    except Exception:
        return info


def capture_active_window_png_bytes(fallback_fullscreen: bool = True) -> Optional[bytes]:
    """
    Captures the active window (preferred) and returns PNG bytes (no file I/O).
    If active window can’t be resolved and fallback_fullscreen is True, captures primary monitor.
    """
    bbox = None

    if gw is not None:
        try:
            w = gw.getActiveWindow()
            if w and w.width > 0 and w.height > 0:
                bbox = {"left": int(w.left), "top": int(w.top), "width": int(w.width), "height": int(w.height)}
        except Exception:
            bbox = None

    with mss.mss() as sct:
        multi_monitor = os.getenv("MULTI_MONITOR", "0") == "1"
        if multi_monitor:
            # Capture bounding box that covers all monitors
            monitors = sct.monitors[1:]
            if monitors:
                left = min(m["left"] for m in monitors)
                top = min(m["top"] for m in monitors)
                right = max(m["left"] + m["width"] for m in monitors)
                bottom = max(m["top"] + m["height"] for m in monitors)
                bbox = {"left": left, "top": top, "width": right - left, "height": bottom - top}

        if bbox is None:
            if not fallback_fullscreen:
                return None
            monitor = sct.monitors[1]  # primary monitor
            bbox = {"left": monitor["left"], "top": monitor["top"], "width": monitor["width"], "height": monitor["height"]}

        sct_img = sct.grab(bbox)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
