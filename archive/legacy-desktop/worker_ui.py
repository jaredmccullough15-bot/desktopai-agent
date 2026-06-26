from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog


APP_TITLE = "Jarvis Worker"
CONFIG_PATH = Path("data") / "worker_ui_config.json"


def default_machine_id() -> str:
    user = os.getenv("USERNAME") or os.getenv("USER") or "unknown"
    host = socket.gethostname() or "unknown-host"
    return f"{user}@{host}"


class WorkerUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("720x500")

        self.process: subprocess.Popen | None = None
        self.selenium_driver = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.config_data: dict = {}

        self._build_ui()
        self._load_config()
        self._pump_logs()
        self.root.after(1200, self._auto_check_for_updates)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}

        frame = tk.Frame(self.root)
        frame.pack(fill="x")

        tk.Label(frame, text="Hub API URL").grid(row=0, column=0, sticky="w", **pad)
        self.api_var = tk.StringVar(value="http://127.0.0.1:8787")
        self.api_entry = tk.Entry(frame, textvariable=self.api_var, width=70)
        self.api_entry.grid(row=0, column=1, sticky="we", **pad)

        tk.Label(frame, text="Machine ID").grid(row=1, column=0, sticky="w", **pad)
        self.machine_var = tk.StringVar(value=default_machine_id())
        self.machine_entry = tk.Entry(frame, textvariable=self.machine_var, width=70)
        self.machine_entry.grid(row=1, column=1, sticky="we", **pad)

        tk.Label(frame, text="Poll (sec)").grid(row=2, column=0, sticky="w", **pad)
        self.poll_var = tk.StringVar(value="2.0")
        self.poll_entry = tk.Entry(frame, textvariable=self.poll_var, width=20)
        self.poll_entry.grid(row=2, column=1, sticky="w", **pad)

        tk.Label(frame, text="Update source").grid(row=3, column=0, sticky="w", **pad)
        self.update_source_var = tk.StringVar(value="")
        self.update_source_entry = tk.Entry(frame, textvariable=self.update_source_var, width=70)
        self.update_source_entry.grid(row=3, column=1, sticky="we", **pad)

        self.auto_update_check_var = tk.BooleanVar(value=True)
        self.auto_update_check = tk.Checkbutton(
            frame,
            text="Check for worker updates on startup",
            variable=self.auto_update_check_var,
            command=self._save_config,
        )
        self.auto_update_check.grid(row=4, column=1, sticky="w", **pad)

        frame.grid_columnconfigure(1, weight=1)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=4)

        self.start_btn = tk.Button(btn_frame, text="Start Ready Mode", command=self.start_worker, bg="#2e7d32", fg="white")
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = tk.Button(btn_frame, text="Stop Worker", command=self.stop_worker, state="disabled", bg="#b71c1c", fg="white")
        self.stop_btn.pack(side="left")

        self.selenium_attach_btn = tk.Button(
            btn_frame,
            text="Open Chrome Debug + Attach Selenium",
            command=self.launch_debug_chrome_with_selenium,
            bg="#1565c0",
            fg="white",
        )
        self.selenium_attach_btn.pack(side="left", padx=(8, 0))

        self.update_btn = tk.Button(btn_frame, text="Self-Update", command=self.self_update)
        self.update_btn.pack(side="right")

        self.status_var = tk.StringVar(value="Status: Idle")
        self.status_lbl = tk.Label(self.root, textvariable=self.status_var, anchor="w")
        self.status_lbl.pack(fill="x", padx=10, pady=(2, 4))

        self.log_box = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, height=22)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._append_log("Worker UI ready. Click 'Start Ready Mode'.")

    def _load_config(self) -> None:
        try:
            if CONFIG_PATH.exists():
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self.config_data = dict(data)
                self.api_var.set(str(data.get("api", self.api_var.get())))
                self.machine_var.set(str(data.get("machine_id", self.machine_var.get())))
                self.poll_var.set(str(data.get("poll", self.poll_var.get())))
                self.update_source_var.set(str(data.get("update_source", self.update_source_var.get())))
                self.auto_update_check_var.set(bool(data.get("auto_update_check", True)))
        except Exception:
            pass

    def _save_config(self) -> None:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = dict(self.config_data)
            payload.update({
                "api": self.api_var.get().strip(),
                "machine_id": self.machine_var.get().strip(),
                "poll": self.poll_var.get().strip(),
                "update_source": self.update_source_var.get().strip(),
                "auto_update_check": bool(self.auto_update_check_var.get()),
            })
            CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self.config_data = payload
        except Exception:
            pass

    def _compute_update_signature(self, source: str) -> str:
        if source.startswith("http://") or source.startswith("https://"):
            req = urllib.request.Request(source, method="HEAD")
            with urllib.request.urlopen(req, timeout=12) as resp:
                etag = str(resp.headers.get("ETag", "")).strip()
                modified = str(resp.headers.get("Last-Modified", "")).strip()
                size = str(resp.headers.get("Content-Length", "")).strip()
                signature = "|".join([part for part in [etag, modified, size] if part])
                return signature or "remote-present"

        path = Path(source)
        if not path.is_absolute():
            path = Path(__file__).parent / path
        path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(f"Update source not found: {path}")
        stat = path.stat()
        return f"local:{path}:{stat.st_size}:{int(stat.st_mtime)}"

    def _auto_check_for_updates(self) -> None:
        if not self.auto_update_check_var.get():
            return

        source = self.update_source_var.get().strip()
        if not source:
            return

        self.log_queue.put("Checking for worker updates...")

        def worker() -> None:
            try:
                signature = self._compute_update_signature(source)
                self.root.after(0, lambda: self._handle_auto_check_result(source, signature, None))
            except Exception as exc:
                self.root.after(0, lambda: self._handle_auto_check_result(source, "", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_auto_check_result(self, source: str, signature: str, error: str | None) -> None:
        if error:
            self.log_queue.put(f"Update check skipped: {error}")
            return

        self.log_queue.put("Update source reachable.")
        last_notified = str(self.config_data.get("update_last_notified_signature", ""))
        if signature == last_notified:
            return

        self.config_data["update_last_notified_signature"] = signature
        self._save_config()

        answer = messagebox.askyesno(
            APP_TITLE,
            "A newer worker package may be available from your configured update source.\nRun self-update now?",
        )
        if answer:
            self.self_update(source)

    def _append_log(self, line: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{timestamp}] {line}\n")
        self.log_box.see(tk.END)

    def _pump_logs(self) -> None:
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(line)
        self.root.after(150, self._pump_logs)

    def _validate(self) -> tuple[str, str, str] | None:
        api = self.api_var.get().strip()
        machine = self.machine_var.get().strip()
        poll = self.poll_var.get().strip() or "2.0"
        if not api:
            messagebox.showerror(APP_TITLE, "Hub API URL is required.")
            return None
        if not machine:
            messagebox.showerror(APP_TITLE, "Machine ID is required.")
            return None
        try:
            float(poll)
        except Exception:
            messagebox.showerror(APP_TITLE, "Poll must be a number (example: 2.0).")
            return None
        return api, machine, poll

    def start_worker(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showinfo(APP_TITLE, "Worker is already running.")
            return

        validated = self._validate()
        if validated is None:
            return
        api, machine, poll = validated

        env = os.environ.copy()
        env["JARVIS_MEMORY_API"] = api
        env["JARVIS_MACHINE_ID"] = machine
        env["JARVIS_WORKER_POLL_INTERVAL"] = poll

        worker_path = Path(__file__).with_name("worker_main.py")
        if not worker_path.exists():
            messagebox.showerror(APP_TITLE, f"worker_main.py not found at {worker_path}")
            return

        self._save_config()

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW

        self.process = subprocess.Popen(
            [sys.executable, str(worker_path)],
            cwd=str(Path(__file__).parent),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=creationflags,
        )

        threading.Thread(target=self._stream_logs, daemon=True).start()
        self.status_var.set(f"Status: Ready (machine_id={machine})")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.log_queue.put(f"Started worker with API={api}")

    @staticmethod
    def _detect_chrome_path() -> str:
        candidates = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ]
        local = os.getenv("LOCALAPPDATA", "").strip()
        if local:
            candidates.append(Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe")

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        raise FileNotFoundError("Google Chrome executable not found on this machine.")

    @staticmethod
    def _is_debug_chrome_ready(port: int) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as resp:
                return bool(resp.read())
        except Exception:
            return False

    def launch_debug_chrome_with_selenium(self) -> None:
        self.log_queue.put("Launching Chrome debug + Selenium attach...")
        threading.Thread(target=self._launch_debug_chrome_with_selenium_async, daemon=True).start()

    def _launch_debug_chrome_with_selenium_async(self) -> None:
        debug_port = int(str(self.config_data.get("chrome_debug_port", 9222) or 9222))
        try:
            from modules.chrome_launcher import launch_debug_chrome

            ready = launch_debug_chrome(
                log=self.log_queue.put,
                port=debug_port,
            )
            if not ready:
                self.log_queue.put(
                    f"[ChromeLauncher] Could not reach Chrome debug endpoint on port {debug_port}. "
                    "Close all Chrome windows and try again."
                )
                return

            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options

            options = Options()
            options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
            options.add_experimental_option("detach", True)

            self.selenium_driver = webdriver.Chrome(options=options)
            self.log_queue.put("Selenium attached to debug Chrome successfully.")
        except Exception as exc:
            self.log_queue.put(f"Chrome/Selenium attach failed: {exc}")

    def _stream_logs(self) -> None:
        proc = self.process
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            text = line.strip()
            if text:
                self.log_queue.put(text)
        code = proc.poll()
        self.log_queue.put(f"Worker process exited (code={code})")
        self.root.after(0, self._mark_stopped)

    def _mark_stopped(self) -> None:
        self.status_var.set("Status: Stopped")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def stop_worker(self) -> None:
        if not self.process or self.process.poll() is not None:
            self._mark_stopped()
            return
        self.log_queue.put("Stopping worker...")
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except Exception:
            self.process.kill()
        self._mark_stopped()

    def self_update(self, package_ref: str | None = None) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno(APP_TITLE, "Worker is running. Stop worker and continue update?"):
                return
            self.stop_worker()

        if not package_ref:
            choice = messagebox.askyesnocancel(
                APP_TITLE,
                "Use YES to choose a local zip file.\nUse NO to paste a zip URL."
            )
            if choice is None:
                return

            if choice:
                picked = filedialog.askopenfilename(
                    title="Select Jarvis Worker Package zip",
                    filetypes=[("Zip files", "*.zip"), ("All files", "*.*")],
                )
                if not picked:
                    return
                package_ref = picked
            else:
                entered = simpledialog.askstring(APP_TITLE, "Paste package zip URL:")
                if not entered:
                    return
                package_ref = entered.strip()

        updater = Path(__file__).with_name("update_worker.ps1")
        if not updater.exists():
            messagebox.showerror(APP_TITLE, f"update_worker.ps1 not found at {updater}")
            return

        self.config_data["update_source"] = str(package_ref).strip()
        self._save_config()

        command = (
            f'powershell -NoProfile -ExecutionPolicy Bypass -File "{updater}" '
            f'-Package "{package_ref}"'
        )
        try:
            subprocess.Popen(command, cwd=str(Path(__file__).parent), shell=True)
            self.log_queue.put("Started self-update in a new PowerShell window.")
            self.log_queue.put("After update completes, reopen Worker UI and Start Ready Mode.")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not start updater: {exc}")

    def _on_close(self) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno(APP_TITLE, "Worker is running. Stop and close?"):
                return
            self.stop_worker()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = WorkerUI(root)
    root.mainloop()
