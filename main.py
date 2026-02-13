import os
import re
import threading
import time
import difflib
import pyautogui
import customtkinter as ctk
import speech_recognition as sr
from modules.brain import process_one_turn
from modules.memory import (
    add_memory_note,
    list_process_docs,
    remove_process_doc,
    add_password_entry,
    list_password_entries,
    remove_password_entry,
    add_web_link,
    list_web_links,
    remove_web_link,
    find_password_entry,
    find_web_link,
)
from modules.actions import fill_login_fields, selenium_get_input_value_by_label
from modules.vision import get_active_window_info
from modules.procedures import (
    get_monitor_choices,
    list_procedures,
    delete_procedure,
    ProcedureRecorder,
    run_procedure,
    run_procedure_loop,
    find_text_position,
)
from modules.data_store import (
    ingest_excel,
    list_datasets,
    set_active_dataset,
    get_active_dataset,
    remove_dataset,
    lookup_writing_agent,
    extract_agent_fields,
)
import sys
from tkinter import filedialog, Listbox, END, simpledialog, messagebox
from docx import Document
from pptx import Presentation
from openai import OpenAI
import sounddevice as sd
import soundfile as sf
import io
from datetime import datetime
try:
    import pytesseract
except Exception:
    pytesseract = None
try:
    import mss
    from PIL import Image
except Exception:
    mss = None
    Image = None
print(sys.path)

# --- 1. SETTINGS & STYLES ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Initialize Voice for the UI (OpenAI TTS)
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
tts_client = OpenAI(api_key=_OPENAI_API_KEY) if _OPENAI_API_KEY else None
TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")

def speak(text):
    """Simple UI-level speech."""
    if not text:
        return
    if tts_client is None:
        return
    try:
        resp = tts_client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=text,
        )
        audio_bytes = resp.read()
        data, samplerate = sf.read(io.BytesIO(audio_bytes), dtype="float32")
        sd.play(data, samplerate)
        sd.wait()
    except Exception:
        pass

def log_line(message: str) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("data/agent.log", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass

# --- 2. GLOBAL MEMORY ---
# This list persists as long as the program is open
agent_memory = [] 

class SmartAgentHUD(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Setup
        self.title("Gemini 2026 Smart HUD")
        self.geometry("900x520+40+40")
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.95)

        # Layout frames
        self.sidebar = ctk.CTkFrame(self, width=160)
        self.sidebar.pack(side="left", fill="y")

        self.main_area = ctk.CTkFrame(self)
        self.main_area.pack(side="right", fill="both", expand=True)

        # Sidebar menu
        self.menu_label = ctk.CTkLabel(self.sidebar, text="MENU", font=("Helvetica", 14, "bold"))
        self.menu_label.pack(pady=(15, 10))

        self.menu_chat = ctk.CTkButton(self.sidebar, text="Chat", command=lambda: self._show_frame("chat"))
        self.menu_chat.pack(pady=5, padx=10, fill="x")

        self.menu_docs = ctk.CTkButton(self.sidebar, text="Process Docs", command=lambda: self._show_frame("docs"))
        self.menu_docs.pack(pady=5, padx=10, fill="x")

        self.menu_passwords = ctk.CTkButton(self.sidebar, text="Passwords", command=lambda: self._show_frame("passwords"))
        self.menu_passwords.pack(pady=5, padx=10, fill="x")

        self.menu_procedures = ctk.CTkButton(self.sidebar, text="Procedures", command=lambda: self._show_frame("procedures"))
        self.menu_procedures.pack(pady=5, padx=10, fill="x")

        self.menu_data = ctk.CTkButton(self.sidebar, text="Data", command=lambda: self._show_frame("data"))
        self.menu_data.pack(pady=5, padx=10, fill="x")

        self.menu_links = ctk.CTkButton(self.sidebar, text="Web Links", command=lambda: self._show_frame("links"))
        self.menu_links.pack(pady=5, padx=10, fill="x")

        # Chat frame
        self.chat_frame = ctk.CTkFrame(self.main_area)
        self.chat_frame.pack(fill="both", expand=True)

        self.label = ctk.CTkLabel(self.chat_frame, text="🤖 SMART COMPANION", font=("Helvetica", 18, "bold"))
        self.label.pack(pady=10)

        self.chat_display = ctk.CTkTextbox(self.chat_frame, width=680, height=260)
        self.chat_display.pack(pady=5, padx=10, fill="both", expand=True)
        self.chat_display.insert("0.0", "System: Connected. Waiting for voice command...\n")

        self.input_entry = ctk.CTkEntry(self.chat_frame, width=680, placeholder_text="Type a command...")
        self.input_entry.pack(pady=5, padx=10, fill="x")
        self.input_entry.bind("<Return>", self._on_send)

        self.send_button = ctk.CTkButton(self.chat_frame, text="Send", command=self._on_send, height=32)
        self.send_button.pack(pady=5)

        self.mic_button = ctk.CTkButton(self.chat_frame, text="🎤 Speak to Agent", command=self.start_voice_thread, height=40)
        self.mic_button.pack(pady=10)

        # Docs frame
        self.docs_frame = ctk.CTkFrame(self.main_area)

        self.docs_label = ctk.CTkLabel(self.docs_frame, text="Process Docs", font=("Helvetica", 16, "bold"))
        self.docs_label.pack(pady=(10, 5))

        self.upload_button = ctk.CTkButton(self.docs_frame, text="Upload Process Doc", command=self._on_upload_doc, height=32)
        self.upload_button.pack(pady=5)

        self.docs_list = Listbox(self.docs_frame, width=90, height=10)
        self.docs_list.pack(pady=8, padx=10, fill="both", expand=True)

        self.docs_refresh = ctk.CTkButton(self.docs_frame, text="Refresh Docs", command=self._refresh_process_docs, height=28)
        self.docs_refresh.pack(pady=(0, 5))

        self.docs_remove = ctk.CTkButton(self.docs_frame, text="Remove Selected Doc", command=self._remove_selected_doc, height=28)
        self.docs_remove.pack(pady=(0, 10))

        # Passwords frame
        self.passwords_frame = ctk.CTkFrame(self.main_area)

        self.passwords_label = ctk.CTkLabel(self.passwords_frame, text="Passwords", font=("Helvetica", 16, "bold"))
        self.passwords_label.pack(pady=(10, 5))

        self.pw_label_entry = ctk.CTkEntry(self.passwords_frame, width=680, placeholder_text="Label (e.g., Work Email)")
        self.pw_label_entry.pack(pady=4, padx=10, fill="x")

        self.pw_url_entry = ctk.CTkEntry(self.passwords_frame, width=680, placeholder_text="Web address (e.g., https://example.com)")
        self.pw_url_entry.pack(pady=4, padx=10, fill="x")

        self.pw_user_entry = ctk.CTkEntry(self.passwords_frame, width=680, placeholder_text="Username or email")
        self.pw_user_entry.pack(pady=4, padx=10, fill="x")

        self.pw_value_entry = ctk.CTkEntry(self.passwords_frame, width=680, placeholder_text="Password", show="*")
        self.pw_value_entry.pack(pady=4, padx=10, fill="x")

        self.pw_save_button = ctk.CTkButton(self.passwords_frame, text="Save Password", command=self._save_password_entry, height=32)
        self.pw_save_button.pack(pady=6)

        self.passwords_list = Listbox(self.passwords_frame, width=90, height=10)
        self.passwords_list.pack(pady=8, padx=10, fill="both", expand=True)

        self.passwords_refresh = ctk.CTkButton(self.passwords_frame, text="Refresh Passwords", command=self._refresh_password_entries, height=28)
        self.passwords_refresh.pack(pady=(0, 5))

        self.passwords_remove = ctk.CTkButton(self.passwords_frame, text="Remove Selected", command=self._remove_selected_password_entry, height=28)
        self.passwords_remove.pack(pady=(0, 10))

        # Procedures frame
        self.procedures_frame = ctk.CTkFrame(self.main_area)

        self.procedures_label = ctk.CTkLabel(self.procedures_frame, text="Procedures", font=("Helvetica", 16, "bold"))
        self.procedures_label.pack(pady=(10, 5))

        self.proc_name_entry = ctk.CTkEntry(self.procedures_frame, width=680, placeholder_text="Procedure name")
        self.proc_name_entry.pack(pady=4, padx=10, fill="x")

        self.proc_monitor_label = ctk.CTkLabel(self.procedures_frame, text="Select monitor")
        self.proc_monitor_label.pack(pady=(6, 2))

        self.proc_monitor_var = ctk.StringVar(value="")
        self.proc_monitor_options = []
        self.proc_monitor_menu = ctk.CTkOptionMenu(self.procedures_frame, values=self.proc_monitor_options, variable=self.proc_monitor_var)
        self.proc_monitor_menu.pack(pady=4, padx=10, fill="x")

        self.proc_monitor_refresh = ctk.CTkButton(self.procedures_frame, text="Refresh Monitors", command=self._refresh_monitor_choices, height=28)
        self.proc_monitor_refresh.pack(pady=(0, 6))

        self.proc_record_row = ctk.CTkFrame(self.procedures_frame)
        self.proc_record_row.pack(pady=(0, 6), padx=10, fill="x")

        self.proc_start_button = ctk.CTkButton(self.proc_record_row, text="Start Recording", command=self._start_procedure_recording, height=32)
        self.proc_start_button.pack(side="left", padx=(0, 6), expand=True, fill="x")

        self.proc_stop_button = ctk.CTkButton(self.proc_record_row, text="Stop Recording", command=self._stop_procedure_recording, height=32)
        self.proc_stop_button.pack(side="left", padx=(0, 6), expand=True, fill="x")

        self.proc_add_checkpoint = ctk.CTkButton(self.proc_record_row, text="Add Checkpoint", command=self._add_procedure_checkpoint, height=32)
        self.proc_add_checkpoint.pack(side="left", expand=True, fill="x")

        self.proc_status = ctk.CTkLabel(self.procedures_frame, text="Status: Idle")
        self.proc_status.pack(pady=(0, 6))

        self.proc_guided_var = ctk.BooleanVar(value=False)
        self.proc_guided_toggle = ctk.CTkCheckBox(self.procedures_frame, text="Guided learning mode", variable=self.proc_guided_var)
        self.proc_guided_toggle.pack(pady=(0, 4))

        self.proc_pause_var = ctk.BooleanVar(value=True)
        self.proc_pause_toggle = ctk.CTkCheckBox(self.procedures_frame, text="Pause on checkpoints", variable=self.proc_pause_var)
        self.proc_pause_toggle.pack(pady=(0, 4))

        self.proc_live_var = ctk.BooleanVar(value=True)
        self.proc_live_toggle = ctk.CTkCheckBox(self.procedures_frame, text="Live narration matching", variable=self.proc_live_var)
        self.proc_live_toggle.pack(pady=(0, 4))

        self.procedures_list = Listbox(self.procedures_frame, width=90, height=8, selectmode="extended")
        self.procedures_list.pack(pady=8, padx=10, fill="both", expand=True)

        self.proc_actions_row = ctk.CTkFrame(self.procedures_frame)
        self.proc_actions_row.pack(pady=(0, 6), padx=10, fill="x")

        self.proc_refresh = ctk.CTkButton(self.proc_actions_row, text="Refresh", command=self._refresh_procedures, height=28)
        self.proc_refresh.pack(side="left", padx=(0, 6), expand=True, fill="x")

        self.proc_run = ctk.CTkButton(self.proc_actions_row, text="Run Selected", command=self._run_selected_procedure, height=28)
        self.proc_run.pack(side="left", padx=(0, 6), expand=True, fill="x")

        self.proc_remove = ctk.CTkButton(self.proc_actions_row, text="Delete Selected", command=self._remove_selected_procedure, height=28)
        self.proc_remove.pack(side="left", expand=True, fill="x")

        self.proc_queue_label = ctk.CTkLabel(self.procedures_frame, text="Run Order")
        self.proc_queue_label.pack(pady=(6, 2))

        self.proc_queue_list = Listbox(self.procedures_frame, width=90, height=8)
        self.proc_queue_list.pack(pady=6, padx=10, fill="both", expand=True)

        self.proc_queue_row = ctk.CTkFrame(self.procedures_frame)
        self.proc_queue_row.pack(pady=(0, 6), padx=10, fill="x")

        self.proc_queue_add = ctk.CTkButton(
            self.proc_queue_row,
            text="Add Selected To Queue",
            command=self._add_selected_procedures_to_queue,
            height=28,
        )
        self.proc_queue_add.pack(side="left", padx=(0, 6), expand=True, fill="x")

        self.proc_queue_up = ctk.CTkButton(
            self.proc_queue_row,
            text="Move Up",
            command=self._move_queue_up,
            height=28,
        )
        self.proc_queue_up.pack(side="left", padx=(0, 6), expand=True, fill="x")

        self.proc_queue_down = ctk.CTkButton(
            self.proc_queue_row,
            text="Move Down",
            command=self._move_queue_down,
            height=28,
        )
        self.proc_queue_down.pack(side="left", expand=True, fill="x")

        self.proc_queue_row2 = ctk.CTkFrame(self.procedures_frame)
        self.proc_queue_row2.pack(pady=(0, 6), padx=10, fill="x")

        self.proc_queue_run = ctk.CTkButton(
            self.proc_queue_row2,
            text="Run Queue",
            command=self._run_procedure_queue,
            height=28,
        )
        self.proc_queue_run.pack(side="left", padx=(0, 6), expand=True, fill="x")

        self.proc_queue_stop = ctk.CTkButton(
            self.proc_queue_row2,
            text="Stop Queue",
            command=self._stop_procedure_queue,
            height=28,
        )
        self.proc_queue_stop.pack(side="left", padx=(0, 6), expand=True, fill="x")

        self.proc_queue_clear = ctk.CTkButton(
            self.proc_queue_row2,
            text="Clear Queue",
            command=self._clear_procedure_queue,
            height=28,
        )
        self.proc_queue_clear.pack(side="left", expand=True, fill="x")

        self.proc_loop_row = ctk.CTkFrame(self.procedures_frame)
        self.proc_loop_row.pack(pady=(0, 8), padx=10, fill="x")

        self.proc_repeat_entry = ctk.CTkEntry(self.proc_loop_row, width=220, placeholder_text="Repeat count (0 = until stop)")
        self.proc_repeat_entry.pack(side="left", padx=(0, 6), expand=True, fill="x")

        self.proc_delay_entry = ctk.CTkEntry(self.proc_loop_row, width=220, placeholder_text="Delay seconds (default 1)")
        self.proc_delay_entry.pack(side="left", padx=(0, 6), expand=True, fill="x")

        self.proc_run_loop = ctk.CTkButton(self.proc_loop_row, text="Run Loop", command=self._run_selected_procedure_loop, height=28)
        self.proc_run_loop.pack(side="left", padx=(0, 6), expand=True, fill="x")

        self.proc_stop_loop = ctk.CTkButton(self.proc_loop_row, text="Stop Loop", command=self._stop_procedure_loop, height=28)
        self.proc_stop_loop.pack(side="left", expand=True, fill="x")

        # Data frame
        self.data_frame = ctk.CTkFrame(self.main_area)

        self.data_label = ctk.CTkLabel(self.data_frame, text="Data Sets", font=("Helvetica", 16, "bold"))
        self.data_label.pack(pady=(10, 5))

        self.data_name_entry = ctk.CTkEntry(self.data_frame, width=680, placeholder_text="Dataset name (optional)")
        self.data_name_entry.pack(pady=4, padx=10, fill="x")

        self.data_upload_button = ctk.CTkButton(self.data_frame, text="Upload Excel Sheet", command=self._on_upload_excel, height=32)
        self.data_upload_button.pack(pady=5)

        self.data_active_label = ctk.CTkLabel(self.data_frame, text="Active: (none)")
        self.data_active_label.pack(pady=(2, 6))

        self.data_list = Listbox(self.data_frame, width=90, height=10)
        self.data_list.pack(pady=8, padx=10, fill="both", expand=True)

        self.data_set_active = ctk.CTkButton(self.data_frame, text="Set Active Dataset", command=self._set_active_dataset, height=28)
        self.data_set_active.pack(pady=(0, 5))

        self.data_remove = ctk.CTkButton(self.data_frame, text="Remove Selected", command=self._remove_selected_dataset, height=28)
        self.data_remove.pack(pady=(0, 10))

        # Links frame
        self.links_frame = ctk.CTkFrame(self.main_area)

        self.links_label = ctk.CTkLabel(self.links_frame, text="Web Links", font=("Helvetica", 16, "bold"))
        self.links_label.pack(pady=(10, 5))

        self.link_name_entry = ctk.CTkEntry(self.links_frame, width=680, placeholder_text="Link name (e.g., Infusionsoft)")
        self.link_name_entry.pack(pady=4, padx=10, fill="x")

        self.link_url_entry = ctk.CTkEntry(self.links_frame, width=680, placeholder_text="URL (e.g., https://app.infusionsoft.com)")
        self.link_url_entry.pack(pady=4, padx=10, fill="x")

        self.link_save = ctk.CTkButton(self.links_frame, text="Save Web Link", command=self._save_web_link, height=32)
        self.link_save.pack(pady=6)

        self.links_list = Listbox(self.links_frame, width=90, height=10)
        self.links_list.pack(pady=8, padx=10, fill="both", expand=True)

        self.links_refresh = ctk.CTkButton(self.links_frame, text="Refresh Links", command=self._refresh_web_links, height=28)
        self.links_refresh.pack(pady=(0, 5))

        self.links_remove = ctk.CTkButton(self.links_frame, text="Remove Selected", command=self._remove_selected_web_link, height=28)
        self.links_remove.pack(pady=(0, 10))

        self._list_microphones()
        self._refresh_process_docs()
        self._refresh_password_entries()
        self._refresh_procedures()
        self._refresh_monitor_choices()
        self._refresh_datasets()
        self._refresh_web_links()
        self._procedure_recorder = None
        self.proc_stop_button.configure(state="disabled")
        self.proc_add_checkpoint.configure(state="disabled")
        self._procedure_loop_stop = threading.Event()
        self.proc_stop_loop.configure(state="disabled")
        self._guided_voice_stop = threading.Event()
        self._guided_voice_thread = None
        self._procedure_queue_stop = threading.Event()
        self.proc_queue_stop.configure(state="disabled")

    def _list_microphones(self):
        try:
            names = sr.Microphone.list_microphone_names()
            if not names:
                self.update_chat("System", "No microphone devices detected.")
                return
            self.update_chat("System", "Detected microphones:")
            for idx, name in enumerate(names):
                self.update_chat("System", f"  [{idx}] {name}")
            self.update_chat("System", "Set MIC_INDEX env var to choose a device.")
        except Exception as e:
            self.update_chat("System", f"Mic list error: {str(e)}")

    def _show_frame(self, name: str):
        self.chat_frame.pack_forget()
        self.docs_frame.pack_forget()
        self.passwords_frame.pack_forget()
        self.procedures_frame.pack_forget()
        self.data_frame.pack_forget()
        self.links_frame.pack_forget()
        if name == "docs":
            self.docs_frame.pack(fill="both", expand=True)
        elif name == "passwords":
            self.passwords_frame.pack(fill="both", expand=True)
        elif name == "procedures":
            self.procedures_frame.pack(fill="both", expand=True)
            self._refresh_monitor_choices()
        elif name == "data":
            self.data_frame.pack(fill="both", expand=True)
            self._refresh_datasets()
        elif name == "links":
            self.links_frame.pack(fill="both", expand=True)
            self._refresh_web_links()
        else:
            self.chat_frame.pack(fill="both", expand=True)

    def update_chat(self, sender, message):
        """Appends text to the HUD display."""
        self.chat_display.insert("end", f"{sender}: {message}\n")
        self.chat_display.see("end")
        if sender == "System":
            log_line(f"System: {message}")

    def start_voice_thread(self):
        """Runs listening in background so UI stays smooth."""
        threading.Thread(target=self.listen_and_process, daemon=True).start()

    def _on_upload_doc(self):
        file_path = filedialog.askopenfilename(
            title="Select a process document",
            filetypes=[("Word or PowerPoint", "*.docx *.pptx"), ("All files", "*.*")],
        )
        if not file_path:
            return
        threading.Thread(target=self._ingest_process_doc, args=(file_path,), daemon=True).start()

    def _ingest_process_doc(self, file_path: str):
        self.upload_button.configure(state="disabled")
        try:
            text = self._read_process_doc(file_path)
            if not text.strip():
                self.update_chat("System", "No readable text found in document.")
                return
            add_memory_note({"type": "process_doc", "source": file_path, "content": text})
            self.update_chat("System", "Process document saved to memory.")
            self._refresh_process_docs()
        except Exception as e:
            self.update_chat("System", f"Upload error: {str(e)}")
        finally:
            self.upload_button.configure(state="normal")

    def _refresh_process_docs(self):
        try:
            self.docs_list.delete(0, END)
            for src in list_process_docs():
                self.docs_list.insert(END, src)
        except Exception as e:
            self.update_chat("System", f"Doc list error: {str(e)}")

    def _remove_selected_doc(self):
        try:
            selection = self.docs_list.curselection()
            if not selection:
                self.update_chat("System", "No document selected.")
                return
            source = self.docs_list.get(selection[0])
            if remove_process_doc(source):
                self.update_chat("System", "Removed process document.")
                self._refresh_process_docs()
            else:
                self.update_chat("System", "Could not remove document.")
        except Exception as e:
            self.update_chat("System", f"Remove error: {str(e)}")

    def _save_password_entry(self):
        label = self.pw_label_entry.get().strip()
        url = self.pw_url_entry.get().strip()
        username = self.pw_user_entry.get().strip()
        password = self.pw_value_entry.get().strip()
        if not label or not url or not username or not password:
            self.update_chat("System", "Please fill in label, web address, username/email, and password.")
            return
        add_password_entry(label, url, username, password)
        self.update_chat("System", "Password saved.")
        self.pw_label_entry.delete(0, "end")
        self.pw_url_entry.delete(0, "end")
        self.pw_user_entry.delete(0, "end")
        self.pw_value_entry.delete(0, "end")
        self._refresh_password_entries()

    def _refresh_password_entries(self):
        try:
            self.passwords_list.delete(0, END)
            self._password_cache = list_password_entries()
            for entry in self._password_cache:
                label = entry.get("label") or "(no label)"
                url = entry.get("url") or ""
                username = entry.get("username") or ""
                self.passwords_list.insert(END, f"{label} | {url} | {username}")
        except Exception as e:
            self.update_chat("System", f"Password list error: {str(e)}")

    def _remove_selected_password_entry(self):
        try:
            selection = self.passwords_list.curselection()
            if not selection:
                self.update_chat("System", "No password selected.")
                return
            entry = getattr(self, "_password_cache", [])[selection[0]]
            label = entry.get("label")
            url = entry.get("url")
            if remove_password_entry(label, url):
                self.update_chat("System", "Removed password entry.")
                self._refresh_password_entries()
            else:
                self.update_chat("System", "Could not remove password entry.")
        except Exception as e:
            self.update_chat("System", f"Password remove error: {str(e)}")

    def _refresh_procedures(self):
        try:
            self.procedures_list.delete(0, END)
            self._procedure_cache = list_procedures()
            for name in self._procedure_cache:
                self.procedures_list.insert(END, name)
        except Exception as e:
            self.update_chat("System", f"Procedure list error: {str(e)}")

    def _refresh_monitor_choices(self):
        try:
            choices = get_monitor_choices()
            self.proc_monitor_options = [label for _, label in choices]
            if not self.proc_monitor_options:
                self.proc_monitor_options = ["1: Primary"]
            self.proc_monitor_menu.configure(values=self.proc_monitor_options)
            current = self.proc_monitor_var.get()
            if current not in self.proc_monitor_options:
                self.proc_monitor_var.set(self.proc_monitor_options[0])
        except Exception as e:
            self.update_chat("System", f"Monitor list error: {str(e)}")

    def _start_procedure_recording(self):
        name = self.proc_name_entry.get().strip()
        if not name:
            self.proc_status.configure(text="Status: Enter a procedure name")
            self.update_chat("System", "Enter a procedure name before recording.")
            return
        if getattr(self, "_procedure_recorder", None) is not None:
            self.proc_status.configure(text="Status: Recording already active")
            self.update_chat("System", "Recording is already in progress.")
            return
        monitor_label = self.proc_monitor_var.get()
        if not monitor_label:
            self.proc_status.configure(text="Status: Select a monitor")
            self.update_chat("System", "Select a monitor before recording.")
            return
        monitor_index = 1
        for idx, label in get_monitor_choices():
            if label == monitor_label:
                monitor_index = idx
                break
        try:
            self._procedure_recorder = ProcedureRecorder(name=name, monitor_index=monitor_index, fps=2)
            self._procedure_recorder.start()
            self.proc_start_button.configure(state="disabled")
            self.proc_stop_button.configure(state="normal")
            if self.proc_guided_var.get():
                self.proc_add_checkpoint.configure(state="normal")
                self._start_guided_voice_recording()
            self.proc_status.configure(text=f"Status: Recording (monitor {monitor_index})")
            self.update_chat("System", f"Recording procedure '{name}' on monitor {monitor_index}.")
        except Exception as e:
            self._procedure_recorder = None
            self.proc_status.configure(text="Status: Recording failed")
            self.update_chat("System", f"Recording failed: {str(e)}")

    def _stop_procedure_recording(self):
        recorder = getattr(self, "_procedure_recorder", None)
        if recorder is None:
            self.update_chat("System", "No active recording.")
            return
        try:
            self._stop_guided_voice_recording()
            info = recorder.stop()
            self._procedure_recorder = None
            self.proc_start_button.configure(state="normal")
            self.proc_stop_button.configure(state="disabled")
            self.proc_add_checkpoint.configure(state="disabled")
            self.proc_status.configure(text="Status: Idle")
            self.update_chat("System", f"Procedure saved: {info.name}.")
            if info.video_path is None:
                self.update_chat("System", "Video writer unavailable. Frames were saved instead.")
            self._refresh_procedures()
        except Exception as e:
            self._stop_guided_voice_recording()
            self._procedure_recorder = None
            self.proc_start_button.configure(state="normal")
            self.proc_stop_button.configure(state="disabled")
            self.proc_add_checkpoint.configure(state="disabled")
            self.proc_status.configure(text="Status: Idle")
            self.update_chat("System", f"Stop failed: {str(e)}")

    def _start_guided_voice_recording(self):
        if self._guided_voice_thread is not None:
            return
        self._guided_voice_stop.clear()
        self._guided_voice_thread = threading.Thread(target=self._guided_voice_loop, daemon=True)
        self._guided_voice_thread.start()

    def _stop_guided_voice_recording(self):
        self._guided_voice_stop.set()
        self._guided_voice_thread = None

    def _guided_voice_loop(self):
        recorder = getattr(self, "_procedure_recorder", None)
        if recorder is None:
            return
        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8
        try:
            mic_index = os.getenv("MIC_INDEX")
            mic_names = sr.Microphone.list_microphone_names()
            if mic_index is not None and mic_index.strip().isdigit():
                idx = int(mic_index)
                if 0 <= idx < len(mic_names):
                    mic = sr.Microphone(device_index=idx)
                else:
                    self.update_chat("System", "Guided voice: MIC_INDEX out of range.")
                    return
            else:
                mic = sr.Microphone()
        except Exception as e:
            self.update_chat("System", f"Guided voice mic error: {type(e).__name__}")
            return

        with mic as source:
            try:
                recognizer.adjust_for_ambient_noise(source, duration=0.6)
            except Exception:
                pass
            while not self._guided_voice_stop.is_set():
                try:
                    audio = recognizer.listen(source, timeout=2, phrase_time_limit=6)
                    text = recognizer.recognize_google(audio)
                    if text:
                        recorder.add_checkpoint(f"Voice: {text}")
                        self.update_chat("System", "Voice note saved.")
                except sr.WaitTimeoutError:
                    continue
                except sr.UnknownValueError:
                    continue
                except Exception:
                    continue

    def _add_procedure_checkpoint(self):
        recorder = getattr(self, "_procedure_recorder", None)
        if recorder is None:
            self.update_chat("System", "No active recording.")
            return
        try:
            self.attributes("-topmost", False)
        except Exception:
            pass
        note = simpledialog.askstring(
            "Checkpoint",
            "What should the agent remember at this step?",
            parent=self,
        )
        try:
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
        except Exception:
            pass
        if not note:
            return
        recorder.add_checkpoint(note)
        self.update_chat("System", "Checkpoint saved.")

    def _run_selected_procedure(self):
        try:
            selection = self.procedures_list.curselection()
            if not selection:
                self.update_chat("System", "No procedure selected.")
                return
            name = self.procedures_list.get(selection[0])
            threading.Thread(target=self._run_procedure_thread, args=(name,), daemon=True).start()
        except Exception as e:
            self.update_chat("System", f"Run procedure error: {str(e)}")

    def _run_procedure_thread(self, name: str):
        handler = None
        if self.proc_pause_var.get():
            handler = lambda note, rect: self._handle_checkpoint(note, rect, name)
        ok = run_procedure(name, checkpoint_handler=handler)
        if ok:
            self.update_chat("System", f"Procedure completed: {name}.")
        else:
            self.update_chat("System", f"Procedure failed: {name}.")

    def _add_selected_procedures_to_queue(self):
        try:
            selections = self.procedures_list.curselection()
            if not selections:
                self.update_chat("System", "Select one or more procedures to add to the queue.")
                return
            for index in selections:
                name = self.procedures_list.get(index)
                self.proc_queue_list.insert(END, name)
        except Exception as e:
            self.update_chat("System", f"Queue add error: {str(e)}")

    def _move_queue_up(self):
        selection = self.proc_queue_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index == 0:
            return
        name = self.proc_queue_list.get(index)
        self.proc_queue_list.delete(index)
        self.proc_queue_list.insert(index - 1, name)
        self.proc_queue_list.selection_set(index - 1)

    def _move_queue_down(self):
        selection = self.proc_queue_list.curselection()
        if not selection:
            return
        index = selection[0]
        last_index = self.proc_queue_list.size() - 1
        if index >= last_index:
            return
        name = self.proc_queue_list.get(index)
        self.proc_queue_list.delete(index)
        self.proc_queue_list.insert(index + 1, name)
        self.proc_queue_list.selection_set(index + 1)

    def _clear_procedure_queue(self):
        self.proc_queue_list.delete(0, END)

    def _run_procedure_queue(self):
        if self.proc_queue_list.size() == 0:
            self.update_chat("System", "Queue is empty.")
            return
        self._procedure_queue_stop.clear()
        self.proc_queue_stop.configure(state="normal")
        threading.Thread(target=self._run_procedure_queue_thread, daemon=True).start()

    def _run_procedure_queue_thread(self):
        names = list(self.proc_queue_list.get(0, END))
        for name in names:
            if self._procedure_queue_stop.is_set():
                self.update_chat("System", "Procedure queue stopped.")
                break
            handler = None
            if self.proc_pause_var.get():
                handler = lambda note, rect, proc_name=name: self._handle_checkpoint(note, rect, proc_name)
            ok = run_procedure(name, checkpoint_handler=handler)
            if ok:
                self.update_chat("System", f"Procedure completed: {name}.")
            else:
                self.update_chat("System", f"Procedure failed: {name}.")
                break
        self.proc_queue_stop.configure(state="disabled")

    def _stop_procedure_queue(self):
        self._procedure_queue_stop.set()
        self.proc_queue_stop.configure(state="disabled")

    def _run_selected_procedure_loop(self):
        try:
            selection = self.procedures_list.curselection()
            if not selection:
                self.update_chat("System", "No procedure selected.")
                return
            name = self.procedures_list.get(selection[0])
            repeat_text = self.proc_repeat_entry.get().strip()
            delay_text = self.proc_delay_entry.get().strip()
            repeat_count = int(repeat_text) if repeat_text.isdigit() else 0
            delay_sec = float(delay_text) if delay_text else 1.0
            self._procedure_loop_stop.clear()
            self.proc_stop_loop.configure(state="normal")
            threading.Thread(
                target=self._run_procedure_loop_thread,
                args=(name, repeat_count, delay_sec),
                daemon=True,
            ).start()
        except Exception as e:
            self.update_chat("System", f"Run loop error: {str(e)}")

    def _run_procedure_loop_thread(self, name: str, repeat_count: int, delay_sec: float):
        handler = None
        if self.proc_pause_var.get():
            handler = lambda note, rect, proc_name=name: self._handle_checkpoint(note, rect, proc_name)
        ok = run_procedure_loop(
            name,
            repeat_count=repeat_count,
            delay_sec=delay_sec,
            stop_event=self._procedure_loop_stop,
            checkpoint_handler=handler,
        )
        self.proc_stop_loop.configure(state="disabled")
        if ok:
            if self._procedure_loop_stop.is_set():
                self.update_chat("System", f"Procedure loop stopped: {name}.")
            else:
                self.update_chat("System", f"Procedure loop completed: {name}.")
        else:
            self.update_chat("System", f"Procedure loop failed: {name}.")

    def _stop_procedure_loop(self):
        self._procedure_loop_stop.set()
        self.proc_stop_loop.configure(state="disabled")

    def _remove_selected_procedure(self):
        try:
            selection = self.procedures_list.curselection()
            if not selection:
                self.update_chat("System", "No procedure selected.")
                return
            name = self.procedures_list.get(selection[0])
            if delete_procedure(name):
                self.update_chat("System", "Procedure removed.")
                self._refresh_procedures()
            else:
                self.update_chat("System", "Could not remove procedure.")
        except Exception as e:
            self.update_chat("System", f"Remove procedure error: {str(e)}")

    def _on_upload_excel(self):
        file_path = filedialog.askopenfilename(
            title="Select an Excel file",
            filetypes=[("Excel", "*.xlsx *.xls"), ("All files", "*.*")],
        )
        if not file_path:
            return
        dataset_name = self.data_name_entry.get().strip() or None
        ok, msg = ingest_excel(file_path, dataset_name=dataset_name)
        if ok:
            self.update_chat("System", msg)
        else:
            self.update_chat("System", f"Excel upload error: {msg}")
        self._refresh_datasets()

    def _refresh_datasets(self):
        try:
            self.data_list.delete(0, END)
            for name in list_datasets():
                self.data_list.insert(END, name)
            active = get_active_dataset() or "(none)"
            self.data_active_label.configure(text=f"Active: {active}")
        except Exception as e:
            self.update_chat("System", f"Dataset list error: {str(e)}")

    def _set_active_dataset(self):
        try:
            selection = self.data_list.curselection()
            if not selection:
                self.update_chat("System", "No dataset selected.")
                return
            name = self.data_list.get(selection[0])
            if set_active_dataset(name):
                self.update_chat("System", f"Active dataset set: {name}.")
                self._refresh_datasets()
            else:
                self.update_chat("System", "Could not set active dataset.")
        except Exception as e:
            self.update_chat("System", f"Set active error: {str(e)}")

    def _remove_selected_dataset(self):
        try:
            selection = self.data_list.curselection()
            if not selection:
                self.update_chat("System", "No dataset selected.")
                return
            name = self.data_list.get(selection[0])
            if remove_dataset(name):
                self.update_chat("System", "Dataset removed.")
                self._refresh_datasets()
            else:
                self.update_chat("System", "Could not remove dataset.")
        except Exception as e:
            self.update_chat("System", f"Remove dataset error: {str(e)}")

    def _save_web_link(self):
        name = self.link_name_entry.get().strip()
        url = self.link_url_entry.get().strip()
        if not name or not url:
            self.update_chat("System", "Enter a name and URL.")
            return
        add_web_link(name, url)
        self.update_chat("System", "Web link saved.")
        self.link_name_entry.delete(0, "end")
        self.link_url_entry.delete(0, "end")
        self._refresh_web_links()

    def _refresh_web_links(self):
        try:
            self.links_list.delete(0, END)
            self._links_cache = list_web_links()
            for entry in self._links_cache:
                name = entry.get("name") or ""
                url = entry.get("url") or ""
                self.links_list.insert(END, f"{name} | {url}")
        except Exception as e:
            self.update_chat("System", f"Web link list error: {str(e)}")

    def _remove_selected_web_link(self):
        try:
            selection = self.links_list.curselection()
            if not selection:
                self.update_chat("System", "No web link selected.")
                return
            entry = getattr(self, "_links_cache", [])[selection[0]]
            name = entry.get("name")
            url = entry.get("url")
            if remove_web_link(name, url):
                self.update_chat("System", "Web link removed.")
                self._refresh_web_links()
            else:
                self.update_chat("System", "Could not remove web link.")
        except Exception as e:
            self.update_chat("System", f"Remove web link error: {str(e)}")

    def _handle_checkpoint(self, note: str, monitor_rect: dict, procedure_name: str = "") -> bool:
        note = (note or "").strip()
        if not note:
            return True
        lowered = note.lower()
        if "checkpoint box" in lowered:
            return True
        if self._should_copy_website_field(procedure_name, lowered):
            return self._copy_website_field_to_clipboard()
        if "aor" in lowered and "writing agent" in lowered:
            return self._handle_aor_from_sales_submit(monitor_rect)
        if "password link" in lowered or "use password" in lowered:
            return self._handle_password_link(note)
        m = re.search(r"writing\s+agent\s*=\s*(.+)$", note, re.IGNORECASE)
        if m:
            agent_name = m.group(1).strip()
            return self._handle_writing_agent(agent_name)
        if "vault" in note.lower():
            # Vault is disabled; skip any vault steps.
            return True
        if note.lower().startswith("voice:") and self.proc_live_var.get():
            return self._handle_live_narration(note, monitor_rect)
        if self._should_gate_checkpoint(procedure_name, note, monitor_rect):
            return True
        try:
            return messagebox.askokcancel("Checkpoint", f"{note}\n\nContinue?")
        except Exception:
            return True

    def _maybe_handle_screen_click_command(self, user_text: str) -> bool:
        if not self._ocr_available():
            return False
        target = self._extract_click_target(user_text)
        if not target:
            return False
        ok = self._click_best_text_match(target)
        if ok:
            self.update_chat("System", f"Clicked best match for: {target}")
        else:
            self.update_chat("System", f"No match found for: {target}")
        return True

    def _extract_click_target(self, user_text: str) -> str:
        if not user_text:
            return ""
        text = user_text.strip()
        patterns = [
            r"^click\s+text\s*[:\-]?\s+(.+)$",
            r"^screen\s+click\s*[:\-]?\s+(.+)$",
            r"^find\s+and\s+click\s+(.+)$",
            r"^click\s+on\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and match.group(1).strip():
                return match.group(1).strip(" \"'")
        return ""

    def _click_best_text_match(self, target_text: str) -> bool:
        if not self._ocr_available():
            return False
        target = self._normalize_text(target_text)
        if not target:
            return False

        info = get_active_window_info()
        bbox = None
        if info.get("width") and info.get("height") and info.get("left") is not None:
            bbox = {
                "left": int(info.get("left")),
                "top": int(info.get("top")),
                "width": int(info.get("width")),
                "height": int(info.get("height")),
            }

        with mss.mss() as sct:
            if bbox is None:
                monitor = sct.monitors[1]
                bbox = {
                    "left": monitor["left"],
                    "top": monitor["top"],
                    "width": monitor["width"],
                    "height": monitor["height"],
                }
            img = sct.grab(bbox)

        pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
        data = pytesseract.image_to_data(pil, output_type=pytesseract.Output.DICT, config="--psm 6")

        lines = {}
        count = len(data.get("text", []))
        for i in range(count):
            word = (data["text"][i] or "").strip()
            if not word:
                continue
            line_key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            entry = lines.get(line_key)
            if entry is None:
                lines[line_key] = {
                    "text": word,
                    "left": x,
                    "top": y,
                    "right": x + w,
                    "bottom": y + h,
                }
            else:
                entry["text"] = f"{entry['text']} {word}"
                entry["left"] = min(entry["left"], x)
                entry["top"] = min(entry["top"], y)
                entry["right"] = max(entry["right"], x + w)
                entry["bottom"] = max(entry["bottom"], y + h)

        best = None
        best_score = 0.0
        for entry in lines.values():
            candidate = self._normalize_text(entry["text"])
            if not candidate:
                continue
            score = difflib.SequenceMatcher(None, target, candidate).ratio()
            if target in candidate:
                score += 0.2
            if score > best_score:
                best_score = score
                best = entry

        if best is None or best_score < 0.4:
            return False

        cx = bbox["left"] + (best["left"] + best["right"]) // 2
        cy = bbox["top"] + (best["top"] + best["bottom"]) // 2
        pyautogui.click(cx, cy)
        return True

    def _normalize_text(self, text: str) -> str:
        return " ".join((text or "").lower().split())

    def _should_gate_checkpoint(self, procedure_name: str, note: str, monitor_rect: dict) -> bool:
        proc = (procedure_name or "").lower()
        lowered = (note or "").lower()
        if "gov" not in proc and "gov" not in lowered:
            return False
        rule = re.search(r"if\s+more\s+than\s+(?:one|1)\s+name", note, re.IGNORECASE)
        if not rule:
            return True
        target_name = self._resolve_checkpoint_name(note)
        if not target_name:
            return True
        count = self._count_name_occurrences_in_results(monitor_rect, target_name)
        if count > 1:
            msg = "Multiple names detected. Pause for review?"
            return messagebox.askokcancel("Checkpoint", msg)
        return True

    def _resolve_checkpoint_name(self, note: str) -> str:
        try:
            clip = self.clipboard_get().strip()
            if clip and re.search(r"[A-Za-z]", clip):
                return clip
        except Exception:
            pass
        return ""

    def _should_copy_website_field(self, procedure_name: str, lowered_note: str) -> bool:
        proc = (procedure_name or "").lower()
        if "gov" not in proc and "gov" not in lowered_note:
            return False
        if "website" in lowered_note and "copy" in lowered_note:
            return True
        if "copy" in lowered_note and "field" in lowered_note:
            return True
        return False

    def _copy_website_field_to_clipboard(self) -> bool:
        if self._is_browser_active():
            value = selenium_get_input_value_by_label("website")
            if value:
                try:
                    self.clipboard_clear()
                    self.clipboard_append(value)
                    return True
                except Exception:
                    pass
        if self._ocr_available():
            self._click_input_right_of_label("website")
        try:
            self.clipboard_clear()
        except Exception:
            pass
        for attempt in range(2):
            if attempt > 0:
                pyautogui.click()
                time.sleep(0.15)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.5)
            try:
                clip = self.clipboard_get().strip()
                if clip:
                    return True
            except Exception:
                pass
            time.sleep(0.3)
        messagebox.showinfo("Copy Website", "Click the website field, then click OK to retry the copy.")
        return self._copy_website_field_to_clipboard()

    def _click_input_right_of_label(self, label_text: str) -> bool:
        if not self._ocr_available():
            return False
        label = self._normalize_text(label_text)
        if not label:
            return False

        info = get_active_window_info()
        bbox = None
        if info.get("width") and info.get("height") and info.get("left") is not None:
            bbox = {
                "left": int(info.get("left")),
                "top": int(info.get("top")),
                "width": int(info.get("width")),
                "height": int(info.get("height")),
            }

        with mss.mss() as sct:
            if bbox is None:
                monitor = sct.monitors[1]
                bbox = {
                    "left": monitor["left"],
                    "top": monitor["top"],
                    "width": monitor["width"],
                    "height": monitor["height"],
                }
            img = sct.grab(bbox)

        pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
        data = pytesseract.image_to_data(pil, output_type=pytesseract.Output.DICT, config="--psm 6")

        lines = {}
        count = len(data.get("text", []))
        for i in range(count):
            word = (data["text"][i] or "").strip()
            if not word:
                continue
            line_key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            entry = lines.get(line_key)
            if entry is None:
                lines[line_key] = {
                    "text": word,
                    "left": x,
                    "top": y,
                    "right": x + w,
                    "bottom": y + h,
                }
            else:
                entry["text"] = f"{entry['text']} {word}"
                entry["left"] = min(entry["left"], x)
                entry["top"] = min(entry["top"], y)
                entry["right"] = max(entry["right"], x + w)
                entry["bottom"] = max(entry["bottom"], y + h)

        best = None
        best_score = 0.0
        for entry in lines.values():
            line_text = self._normalize_text(entry["text"])
            if not line_text:
                continue
            score = difflib.SequenceMatcher(None, label, line_text).ratio()
            if label in line_text:
                score += 0.3
            if score > best_score:
                best_score = score
                best = entry

        if best is None or best_score < 0.45:
            return False

        offset_x = 120
        max_x = bbox["left"] + bbox["width"] - 5
        cx = min(max_x, bbox["left"] + best["right"] + offset_x)
        cy = bbox["top"] + (best["top"] + best["bottom"]) // 2
        pyautogui.click(cx, cy)
        time.sleep(0.2)
        return True

    def _count_name_occurrences_in_results(self, monitor_rect: dict, target_name: str) -> int:
        if not self._ocr_available() or not monitor_rect:
            return 0
        target = " ".join(target_name.split()).lower()
        if not target:
            return 0
        try:
            if os.getenv("TESSERACT_CMD"):
                pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")
            with mss.mss() as sct:
                img = sct.grab(monitor_rect)
            pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            text = pytesseract.image_to_string(pil, config="--psm 6")
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            matches = []
            for line in lines:
                normalized = " ".join(line.split()).lower()
                if target in normalized:
                    matches.append(normalized)
            if not matches:
                return 0
            query_removed = False
            results = 0
            for normalized in matches:
                if not query_removed:
                    if normalized == target or len(normalized) <= len(target) + 2:
                        query_removed = True
                        continue
                results += 1
            return results
        except Exception:
            return 0

    def _handle_writing_agent(self, agent_name: str) -> bool:
        record = lookup_writing_agent(agent_name)
        if not record:
            messagebox.showinfo("Writing Agent", f"No match found for '{agent_name}'.")
            return True
        fields = extract_agent_fields(record)
        first_name = fields.get("first_name", "")
        last_name = fields.get("last_name", "")
        npn = fields.get("npn", "")
        msg = f"Fill fields with:\nFirst: {first_name}\nLast: {last_name}\nNPN: {npn}\n\nClick OK to type into current fields."
        if not messagebox.askokcancel("Writing Agent", msg):
            return True
        pyautogui.write(first_name)
        pyautogui.press("tab")
        pyautogui.write(last_name)
        pyautogui.press("tab")
        pyautogui.write(npn)
        return True

    def _handle_password_link(self, note: str) -> bool:
        label = ""
        m = re.search(r"password\s+link\s+(?:for|to)?\s*(.+)$", note, re.IGNORECASE)
        if m:
            label = m.group(1).strip()
        m2 = re.search(r"use\s+password\s+(?:link\s+)?(?:for|to)?\s*(.+)$", note, re.IGNORECASE)
        if m2:
            label = label or m2.group(1).strip()
        if not label:
            label = simpledialog.askstring("Password Link", "Which password label should I use?") or ""
        label = label.strip()
        if not label:
            return True
        entry = find_password_entry(label=label, url=None)
        if not entry:
            messagebox.showinfo("Password Link", f"No password entry found for '{label}'.")
            return True
        url = entry.get("url")
        username = entry.get("username")
        password = entry.get("password")
        if not url:
            return True
        pyautogui.hotkey("ctrl", "l")
        pyautogui.write(url)
        pyautogui.press("enter")
        time.sleep(1.2)
        if username and password:
            fill_login_fields(username, password, submit=False)
        return True

    # Vault handling intentionally disabled.

    def _handle_aor_from_sales_submit(self, monitor_rect: dict) -> bool:
        name = self._extract_writing_agent_name(monitor_rect)
        if not name:
            name = simpledialog.askstring("AOR", "Enter Writing Agent name from Sales & Submit")
        if not name:
            return True
        record = lookup_writing_agent(name)
        if not record:
            messagebox.showinfo("AOR", f"No match found for '{name}'.")
            return True
        fields = extract_agent_fields(record)
        npn = fields.get("npn", "")
        if not npn:
            messagebox.showinfo("AOR", f"No NPN found for '{name}'.")
            return True
        pyautogui.write(npn)
        return True

    def _extract_writing_agent_name(self, monitor_rect: dict) -> str:
        if not self._ocr_available() or not monitor_rect:
            return ""
        try:
            if os.getenv("TESSERACT_CMD"):
                pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")
            with mss.mss() as sct:
                img = sct.grab(monitor_rect)
            pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            text = pytesseract.image_to_string(pil, config="--psm 6")
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            for line in lines:
                if "writing agent" in line.lower():
                    parts = re.split(r"writing\s+agent\s*[:\-]?\s*", line, flags=re.IGNORECASE)
                    if len(parts) > 1 and parts[1].strip():
                        return parts[1].strip().split(" ")[0]
            return ""
        except Exception:
            return ""

    def _handle_live_narration(self, note: str, monitor_rect: dict) -> bool:
        narration = note.split(":", 1)[-1].strip()
        if not narration:
            return True
        screen_text = self._ocr_screen_text(monitor_rect)
        if self._narration_matches_screen(narration, screen_text):
            return True
        msg = f"Narration did not match visible screen text.\n\nNarration: {narration}\n\nContinue anyway?"
        return messagebox.askokcancel("Narration Check", msg)

    def _ocr_screen_text(self, monitor_rect: dict) -> str:
        if not self._ocr_available() or not monitor_rect:
            return ""
        try:
            if os.getenv("TESSERACT_CMD"):
                pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")
            with mss.mss() as sct:
                img = sct.grab(monitor_rect)
            pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            text = pytesseract.image_to_string(pil, config="--psm 6")
            return " ".join(text.split()).lower()
        except Exception:
            return ""

    def _narration_matches_screen(self, narration: str, screen_text: str) -> bool:
        if not screen_text:
            return False
        stop = {"the", "and", "or", "to", "a", "an", "of", "in", "on", "for", "with", "is", "it"}
        words = [w for w in re.split(r"\W+", narration.lower()) if w and w not in stop]
        if not words:
            return False
        hits = sum(1 for w in words if w in screen_text)
        return hits >= max(1, len(words) // 3)

    def _ocr_available(self) -> bool:
        if pytesseract is None or mss is None or Image is None:
            return False
        if os.getenv("TESSERACT_CMD"):
            pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def _is_browser_active(self) -> bool:
        info = get_active_window_info()
        title = (info.get("title") or "").lower()
        if not title:
            return False
        browsers = ["chrome", "edge", "firefox", "brave", "opera"]
        return any(name in title for name in browsers)

    def _read_process_doc(self, file_path: str) -> str:
        if file_path.lower().endswith(".docx"):
            doc = Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs if p.text)
        if file_path.lower().endswith(".pptx"):
            prs = Presentation(file_path)
            chunks = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        chunks.append(shape.text)
            return "\n".join(chunks)
        return ""

    def _on_send(self, event=None):
        text = self.input_entry.get().strip()
        if not text:
            return
        self.input_entry.delete(0, "end")
        threading.Thread(target=self.process_text_input, args=(text,), daemon=True).start()

    def process_text_input(self, user_text: str):
        self.send_button.configure(state="disabled")
        try:
            self.update_chat("You", user_text)
            agent_memory.append({"role": "user", "content": user_text})

            if self._maybe_handle_screen_click_command(user_text):
                return

            result = process_one_turn(user_text, execute_actions=True)
            model_info = result.get("model", {}) or {}
            assistant_text = model_info.get("answer") or ""
            if not assistant_text:
                assistant_text = model_info.get("raw_text") or ""
            if not assistant_text:
                err = model_info.get("error")
                if err:
                    self.update_chat("System", f"Model error: {err}")
                assistant_text = "(No response from model.)"
            self.update_chat("Agent", assistant_text)
            exec_info = result.get("execution", {}) or {}
            if exec_info.get("error"):
                self.update_chat("System", f"Action error: {exec_info.get('error')}")
            elif exec_info.get("executed"):
                add_memory_note({"type": "action", "input": user_text, "result": exec_info.get("result")})
            log_line(f"Action execution: {exec_info}")
            agent_memory.append({"role": "assistant", "content": assistant_text})
            speak(assistant_text or "Okay.")
        except Exception as e:
            self.update_chat("System", f"Error: {str(e)}")
        finally:
            self.send_button.configure(state="normal")

    def listen_and_process(self):
        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8
        recognizer.phrase_threshold = 0.3
        recognizer.non_speaking_duration = 0.5

        try:
            # Allow manual device selection via MIC_INDEX env var
            mic_index = os.getenv("MIC_INDEX")
            mic_names = sr.Microphone.list_microphone_names()
            if mic_index is not None and mic_index.strip().isdigit():
                idx = int(mic_index)
                if 0 <= idx < len(mic_names):
                    mic = sr.Microphone(device_index=idx)
                else:
                    self.update_chat("System", f"MIC_INDEX {idx} is out of range (0-{max(len(mic_names)-1, 0)}). Select a valid index and restart.")
                    return
            else:
                mic = sr.Microphone()
        except Exception as e:
            self.update_chat("System", f"Microphone error: {type(e).__name__}: {repr(e)}")
            return

        with mic as source:
            self.mic_button.configure(state="disabled", fg_color="red", text="Listening...")
            try:
                device_name = getattr(mic, "device_name", None)
                if device_name:
                    self.update_chat("System", f"Using mic: {device_name}")
                if mic_index is not None:
                    self.update_chat("System", f"MIC_INDEX={mic_index}")
                self.update_chat("System", "Calibrating microphone...")
                if getattr(source, "stream", None) is None:
                    self.update_chat("System", "Mic stream not opened. Check MIC_INDEX, Windows privacy permissions, or reinstall PyAudio.")
                    return
                try:
                    recognizer.adjust_for_ambient_noise(source, duration=0.8)
                except Exception as e:
                    self.update_chat("System", f"Mic init error: {type(e).__name__}: {repr(e)}. Check MIC_INDEX/device.")
                    return

                # Capture Voice
                self.update_chat("System", "Speak now...")
                audio = recognizer.listen(source, timeout=15, phrase_time_limit=15)
                user_text = recognizer.recognize_google(audio)
                
                # 1. Update UI and Memory
                self.update_chat("You", user_text)
                agent_memory.append({"role": "user", "content": user_text})

                if self._maybe_handle_screen_click_command(user_text):
                    return
                
                # 2. Run the Smart Brain
                # The brain will now process the whole history and decide to CHAT or ACT
                result = process_one_turn(user_text, execute_actions=True)
                model_info = result.get("model", {}) or {}
                assistant_text = model_info.get("answer") or ""
                if not assistant_text:
                    assistant_text = model_info.get("raw_text") or ""
                if not assistant_text:
                    err = model_info.get("error")
                    if err:
                        self.update_chat("System", f"Model error: {err}")
                    assistant_text = "(No response from model.)"
                self.update_chat("Agent", assistant_text)
                exec_info = result.get("execution", {}) or {}
                if exec_info.get("error"):
                    self.update_chat("System", f"Action error: {exec_info.get('error')}")
                elif exec_info.get("executed"):
                    add_memory_note({"type": "action", "input": user_text, "result": exec_info.get("result")})
                log_line(f"Action execution: {exec_info}")
                agent_memory.append({"role": "assistant", "content": assistant_text})
                speak(assistant_text)

                
            except sr.UnknownValueError:
                self.update_chat("System", "Could not understand audio.")
            except sr.WaitTimeoutError:
                self.update_chat("System", "Listening timed out. Try again and speak a bit sooner.")
            except Exception as e:
                self.update_chat("System", f"Error: {str(e)}")
            finally:
                self.mic_button.configure(state="normal", fg_color="#1f538d", text="🎤 Speak to Agent")

if __name__ == "__main__":
    app = SmartAgentHUD()
    app.mainloop()