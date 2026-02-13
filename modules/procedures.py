import json
import os
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple
import re

import mss
from PIL import Image

try:
    import numpy as np
except Exception:
    np = None

try:
    import imageio.v2 as imageio
except Exception:
    imageio = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    from pynput import mouse, keyboard
except Exception:
    mouse = None
    keyboard = None

import pyautogui

from modules.actions import (
    focus_window_by_title,
    selenium_get_current_url,
    selenium_get_active_input_info,
    selenium_set_input_value,
)
from modules.vision import get_active_window_info

PROCEDURES_DIR = os.path.join("data", "procedures")


def get_monitor_choices() -> List[Tuple[int, str]]:
    choices: List[Tuple[int, str]] = []
    with mss.mss() as sct:
        for idx, m in enumerate(sct.monitors[1:], start=1):
            label = f"{idx}: {m['width']}x{m['height']} @ ({m['left']},{m['top']})"
            choices.append((idx, label))
    if not choices:
        choices.append((1, "1: Primary"))
    return choices


def list_procedures() -> List[str]:
    if not os.path.isdir(PROCEDURES_DIR):
        return []
    names = []
    for name in os.listdir(PROCEDURES_DIR):
        manifest = os.path.join(PROCEDURES_DIR, name, "manifest.json")
        if os.path.isfile(manifest):
            names.append(name)
    return sorted(names)


def delete_procedure(name: str) -> bool:
    name = (name or "").strip()
    if not name:
        return False
    target = os.path.join(PROCEDURES_DIR, name)
    if not os.path.isdir(target):
        return False
    for root, dirs, files in os.walk(target, topdown=False):
        for f in files:
            try:
                os.remove(os.path.join(root, f))
            except Exception:
                pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except Exception:
                pass
    try:
        os.rmdir(target)
    except Exception:
        pass
    return True


@dataclass
class ProcedureInfo:
    name: str
    monitor_index: int
    fps: int
    video_path: Optional[str]
    frames_dir: str
    events: list
    created_at: str


def _load_procedure(name: str) -> Optional[ProcedureInfo]:
    name = (name or "").strip()
    if not name:
        return None
    manifest = os.path.join(PROCEDURES_DIR, name, "manifest.json")
    if not os.path.isfile(manifest):
        return None
    try:
        with open(manifest, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ProcedureInfo(
            name=data.get("name", name),
            monitor_index=int(data.get("monitor_index", 1)),
            fps=int(data.get("fps", 2)),
            video_path=data.get("video_path"),
            frames_dir=data.get("frames_dir", ""),
            events=data.get("events", []),
            created_at=data.get("created_at", ""),
        )
    except Exception:
        return None


class ProcedureRecorder:
    def __init__(self, name: str, monitor_index: int, fps: int = 2) -> None:
        self.name = name
        self.monitor_index = monitor_index
        self.fps = max(1, int(fps))
        self._events = []
        self._recording = False
        self._start_time = 0.0
        self._frame_thread: Optional[threading.Thread] = None
        self._observe_thread: Optional[threading.Thread] = None
        self._mouse_listener = None
        self._keyboard_listener = None
        self._writer = None
        self._frame_count = 0
        self._frame_buffer = []
        self._monitor_rect = None

        self.base_dir = os.path.join(PROCEDURES_DIR, self.name)
        self.frames_dir = os.path.join(self.base_dir, "frames")
        self.video_path = os.path.join(self.base_dir, f"{self.name}.mp4")

    def start(self) -> None:
        if self._recording:
            return
        os.makedirs(self.frames_dir, exist_ok=True)
        self._events = []
        self._recording = True
        self._start_time = time.time()

        self._writer = None
        self._frame_count = 0
        self._frame_buffer = []

        self._monitor_rect = self._get_monitor_rect(self.monitor_index)

        self._frame_thread = threading.Thread(target=self._record_frames, daemon=True)
        self._frame_thread.start()

        self._observe_thread = threading.Thread(target=self._observe_active_window, daemon=True)
        self._observe_thread.start()

        if mouse is not None:
            self._mouse_listener = mouse.Listener(on_click=self._on_click, on_scroll=self._on_scroll)
            self._mouse_listener.start()
        if keyboard is not None:
            self._keyboard_listener = keyboard.Listener(on_press=self._on_press)
            self._keyboard_listener.start()

    def stop(self) -> ProcedureInfo:
        self._recording = False
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        if self._keyboard_listener:
            try:
                self._keyboard_listener.stop()
            except Exception:
                pass
        if self._frame_thread:
            self._frame_thread.join(timeout=2.0)
        if self._observe_thread:
            self._observe_thread.join(timeout=2.0)
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:
                pass

        if self._frame_count < 2 and os.path.isfile(self.video_path):
            try:
                os.remove(self.video_path)
            except Exception:
                pass

        info = ProcedureInfo(
            name=self.name,
            monitor_index=self.monitor_index,
            fps=self.fps,
            video_path=self.video_path if self._writer is not None and self._frame_count >= 2 else None,
            frames_dir=self.frames_dir,
            events=self._events,
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._write_manifest(info)
        return info

    def add_checkpoint(self, note: str) -> None:
        if not self._recording:
            return
        note = (note or "").strip()
        if not note:
            return
        self._events.append({
            "t": round(self._elapsed(), 3),
            "type": "checkpoint",
            "note": note,
        })

    def _write_manifest(self, info: ProcedureInfo) -> None:
        os.makedirs(self.base_dir, exist_ok=True)
        manifest = {
            "name": info.name,
            "monitor_index": info.monitor_index,
            "fps": info.fps,
            "video_path": info.video_path,
            "frames_dir": info.frames_dir,
            "events": info.events,
            "created_at": info.created_at,
        }
        with open(os.path.join(self.base_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def _elapsed(self) -> float:
        return time.time() - self._start_time

    def _on_click(self, x, y, button, pressed):
        if not self._recording or not pressed:
            return
        hint_text = self._capture_hint_text(int(x), int(y))
        self._events.append({
            "t": round(self._elapsed(), 3),
            "type": "click",
            "x": int(x),
            "y": int(y),
            "button": str(button).split(".")[-1],
            "hint_text": hint_text,
        })

    def _on_press(self, key):
        if not self._recording:
            return
        try:
            if hasattr(key, "char") and key.char:
                k = key.char
            else:
                k = str(key).split(".")[-1]
        except Exception:
            k = ""
        if not k:
            return
        self._events.append({
            "t": round(self._elapsed(), 3),
            "type": "key",
            "key": k,
        })

    def _on_scroll(self, x, y, dx, dy):
        if not self._recording:
            return
        self._events.append({
            "t": round(self._elapsed(), 3),
            "type": "scroll",
            "x": int(x),
            "y": int(y),
            "dx": int(dx),
            "dy": int(dy),
        })

    def _record_frames(self) -> None:
        frame_idx = 0
        with mss.mss() as sct:
            monitors = sct.monitors
            if self.monitor_index < 1 or self.monitor_index >= len(monitors):
                monitor = monitors[1]
            else:
                monitor = monitors[self.monitor_index]

            interval = 1.0 / float(self.fps)
            while self._recording:
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                frame_path = os.path.join(self.frames_dir, f"frame_{frame_idx:06d}.png")
                try:
                    img.save(frame_path)
                except Exception:
                    pass

                if np is not None and imageio is not None:
                    try:
                        frame_array = np.array(img)
                        if self._writer is None:
                            self._frame_buffer.append(frame_array)
                            if len(self._frame_buffer) >= 2:
                                self._writer = imageio.get_writer(self.video_path, fps=self.fps)
                                for buffered in self._frame_buffer:
                                    self._writer.append_data(buffered)
                                self._frame_buffer = []
                        else:
                            self._writer.append_data(frame_array)
                    except Exception:
                        pass

                frame_idx += 1
                self._frame_count += 1
                time.sleep(interval)

    def _observe_active_window(self) -> None:
        last_title = ""
        last_url = ""
        last_field_key = ""
        last_field_value = ""
        stable_count = 0
        last_recorded = {}
        while self._recording:
            info = get_active_window_info()
            title = (info.get("title") or "").strip()
            if title and title != last_title:
                self._events.append({
                    "t": round(self._elapsed(), 3),
                    "type": "focus_window",
                    "title": title,
                    "app_hint": self._infer_app_hint(title),
                })
                last_title = title

            if title and "chrome" in title.lower():
                url = selenium_get_current_url()
                if url and url != last_url:
                    self._events.append({
                        "t": round(self._elapsed(), 3),
                        "type": "open_url",
                        "url": url,
                    })
                    last_url = url

                field = selenium_get_active_input_info()
                if field:
                    field_id = str(field.get("id") or "").strip()
                    field_name = str(field.get("name") or "").strip()
                    field_label = str(field.get("label") or "").strip()
                    field_value = str(field.get("value") or "")
                    field_key = field_id or field_name or field_label

                    if field_key:
                        if field_key == last_field_key and field_value == last_field_value:
                            stable_count += 1
                        else:
                            stable_count = 1
                            last_field_key = field_key
                            last_field_value = field_value

                        if stable_count >= 2:
                            last_value = last_recorded.get(field_key)
                            if field_value != last_value:
                                self._events.append({
                                    "t": round(self._elapsed(), 3),
                                    "type": "set_field",
                                    "label": field_label,
                                    "name": field_name,
                                    "id": field_id,
                                    "value": field_value,
                                })
                                last_recorded[field_key] = field_value
                                stable_count = 0

            time.sleep(0.5)

    def _infer_app_hint(self, title: str) -> str:
        lowered = (title or "").lower()
        if "chrome" in lowered:
            return "chrome"
        if "edge" in lowered:
            return "edge"
        if "firefox" in lowered:
            return "firefox"
        if "brave" in lowered:
            return "brave"
        if "opera" in lowered:
            return "opera"
        return (title or "")[:60]

    def _get_monitor_rect(self, index: int) -> dict:
        with mss.mss() as sct:
            monitors = sct.monitors
            if index < 1 or index >= len(monitors):
                return monitors[1]
            return monitors[index]

    def _capture_hint_text(self, x: int, y: int) -> str:
        if pytesseract is None:
            return ""
        rect = self._monitor_rect
        if not rect:
            return ""
        left = max(rect["left"], x - 150)
        top = max(rect["top"], y - 100)
        right = min(rect["left"] + rect["width"], x + 150)
        bottom = min(rect["top"] + rect["height"], y + 100)
        if right <= left or bottom <= top:
            return ""
        try:
            if os.getenv("TESSERACT_CMD"):
                pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")
            with mss.mss() as sct:
                img = sct.grab({"left": left, "top": top, "width": right - left, "height": bottom - top})
            pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            text = pytesseract.image_to_string(pil, config="--psm 6")
            text = " ".join(text.split())
            return text[:80]
        except Exception:
            return ""


def run_procedure(name: str, speed: float = 1.0, checkpoint_handler=None) -> bool:
    info = _load_procedure(name)
    if info is None:
        return False
    events = sorted(info.events, key=lambda e: e.get("t", 0))
    if not events:
        return False

    pyautogui.FAILSAFE = True

    monitor_rect = None
    with mss.mss() as sct:
        monitors = sct.monitors
        if info.monitor_index < 1 or info.monitor_index >= len(monitors):
            monitor_rect = monitors[1]
        else:
            monitor_rect = monitors[info.monitor_index]

    start = time.time()
    for ev in events:
        t = float(ev.get("t", 0)) / max(speed, 0.1)
        while time.time() - start < t:
            time.sleep(0.01)
        if ev.get("type") == "checkpoint":
            note = str(ev.get("note", "")).strip()
            if callable(checkpoint_handler):
                pause_start = time.time()
                should_continue = checkpoint_handler(note, monitor_rect)
                pause_end = time.time()
                start += max(0.0, pause_end - pause_start)
                if should_continue is False:
                    return False
            continue
        if ev.get("type") == "focus_window":
            app_hint = str(ev.get("app_hint", "")).strip()
            title = str(ev.get("title", "")).strip()
            focus_window_by_title(app_hint or title)
            time.sleep(0.2)
            continue
        if ev.get("type") == "open_url":
            url = str(ev.get("url", "")).strip()
            if url:
                focus_window_by_title("chrome")
                time.sleep(0.2)
                pyautogui.hotkey("ctrl", "l")
                time.sleep(0.1)
                pyautogui.write(url, interval=0.02)
                pyautogui.press("enter")
                time.sleep(0.3)
            continue
        if ev.get("type") == "set_field":
            label = str(ev.get("label", "")).strip()
            name = str(ev.get("name", "")).strip()
            element_id = str(ev.get("id", "")).strip()
            value = str(ev.get("value", ""))
            focus_window_by_title("chrome")
            time.sleep(0.2)
            selenium_set_input_value(label, value, name=name, element_id=element_id)
            time.sleep(0.2)
            continue
        if ev.get("type") == "click":
            x = int(ev.get("x", 0))
            y = int(ev.get("y", 0))
            hint_text = str(ev.get("hint_text", "")).strip()
            if hint_text and pytesseract is not None and monitor_rect is not None:
                pos = _find_text_position(hint_text, monitor_rect)
                if pos is None:
                    for _ in range(6):
                        pyautogui.scroll(-500)
                        time.sleep(0.25)
                        pos = _find_text_position(hint_text, monitor_rect)
                        if pos is not None:
                            break
                if pos is not None:
                    pyautogui.click(pos[0], pos[1])
                    continue
            try:
                pyautogui.click(x, y)
            except Exception:
                pass
        elif ev.get("type") == "key":
            key = str(ev.get("key", ""))
            if not key:
                continue
            if len(key) == 1:
                pyautogui.write(key)
            else:
                pyautogui.press(key)
        elif ev.get("type") == "scroll":
            dx = int(ev.get("dx", 0))
            dy = int(ev.get("dy", 0))
            if dy:
                pyautogui.scroll(dy)
            if dx:
                try:
                    pyautogui.hscroll(dx)
                except Exception:
                    pass
    return True


def run_procedure_loop(name: str, repeat_count: int = 0, delay_sec: float = 1.0, stop_event: Optional[threading.Event] = None, checkpoint_handler=None) -> bool:
    """Run a procedure repeatedly. repeat_count=0 means run until stop_event is set."""
    count = 0
    while True:
        if stop_event is not None and stop_event.is_set():
            return True
        ok = run_procedure(name, checkpoint_handler=checkpoint_handler)
        if not ok:
            return False
        count += 1
        if repeat_count > 0 and count >= repeat_count:
            return True
        time.sleep(max(0.1, delay_sec))


def _find_text_position(target_text: str, monitor_rect: dict) -> Optional[Tuple[int, int]]:
    if pytesseract is None:
        return None
    try:
        if os.getenv("TESSERACT_CMD"):
            pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")
        with mss.mss() as sct:
            img = sct.grab(monitor_rect)
        pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
        data = pytesseract.image_to_data(pil, output_type=pytesseract.Output.DICT, config="--psm 6")
        words = [w for w in re.split(r"\s+", target_text) if w]
        if not words:
            return None
        for i, text in enumerate(data.get("text", [])):
            if not text:
                continue
            if words[0].lower() in text.lower():
                x = data.get("left", [0])[i]
                y = data.get("top", [0])[i]
                w = data.get("width", [0])[i]
                h = data.get("height", [0])[i]
                return (monitor_rect["left"] + x + w // 2, monitor_rect["top"] + y + h // 2)
    except Exception:
        return None
    return None


def find_text_position(target_text: str, monitor_rect: dict) -> Optional[Tuple[int, int]]:
    """Public wrapper for OCR-based text lookup."""
    return _find_text_position(target_text, monitor_rect)
