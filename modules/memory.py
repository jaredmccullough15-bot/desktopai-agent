import json
import os

MEMORY_FILE = "data/desktop_memory.json"

def save_location(name, x, y):
    """Saves a coordinate to memory so the AI doesn't have to guess next time."""
    memory = load_memory()
    memory[name.lower()] = {"x": x, "y": y}
    
    if not os.path.exists('data'): os.makedirs('data')
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)
    print(f"--- [Memory] Saved {name} at ({x}, {y}) ---")

def load_memory():
    """Loads all known locations."""
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def get_location(name):
    """Checks if we already know where a file is."""
    memory = load_memory()
    return memory.get(name.lower())


def add_memory_note(note: dict, max_notes: int = 50) -> None:
    """Adds a general memory note for the agent."""
    memory = load_memory()
    notes = memory.get("notes", [])
    notes.append(note)
    memory["notes"] = notes[-max_notes:]

    if not os.path.exists("data"):
        os.makedirs("data")
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)


def get_memory_notes(limit: int = 20) -> list:
    """Returns recent memory notes."""
    memory = load_memory()
    notes = memory.get("notes", [])
    return notes[-limit:]


def list_process_docs() -> list:
    """Returns a list of process_doc sources from memory."""
    memory = load_memory()
    notes = memory.get("notes", [])
    return [n.get("source") for n in notes if isinstance(n, dict) and n.get("type") == "process_doc" and n.get("source")]


def remove_process_doc(source: str) -> bool:
    """Remove a process_doc note by source path."""
    source = (source or "").strip()
    if not source:
        return False
    memory = load_memory()
    notes = memory.get("notes", [])
    new_notes = [n for n in notes if not (isinstance(n, dict) and n.get("type") == "process_doc" and n.get("source") == source)]
    if len(new_notes) == len(notes):
        return False
    memory["notes"] = new_notes
    if not os.path.exists("data"):
        os.makedirs("data")
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)
    return True


def add_password_entry(label: str, url: str, username: str, password: str, max_entries: int = 200) -> None:
    """Adds a password entry to memory."""
    label = (label or "").strip()
    url = (url or "").strip()
    username = (username or "").strip()
    password = (password or "").strip()
    if not label or not url or not username or not password:
        return
    memory = load_memory()
    notes = memory.get("notes", [])
    notes.append({
        "type": "password_entry",
        "label": label,
        "url": url,
        "username": username,
        "password": password,
    })
    memory["notes"] = notes[-max_entries:]

    if not os.path.exists("data"):
        os.makedirs("data")
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)


def list_password_entries() -> list:
    """Returns all stored password entries."""
    memory = load_memory()
    notes = memory.get("notes", [])
    return [
        n for n in notes
        if isinstance(n, dict) and n.get("type") == "password_entry"
           and n.get("label") and n.get("url") and n.get("username") and n.get("password")
    ]


def list_password_entry_summaries() -> list:
    """Returns password entry summaries without the password value."""
    summaries = []
    for entry in list_password_entries():
        summaries.append({
            "label": entry.get("label"),
            "url": entry.get("url"),
            "username": entry.get("username"),
        })
    return summaries


def remove_password_entry(label: str, url: str) -> bool:
    """Remove a password entry by label+url."""
    label = (label or "").strip()
    url = (url or "").strip()
    if not label or not url:
        return False
    memory = load_memory()
    notes = memory.get("notes", [])
    new_notes = [
        n for n in notes
        if not (isinstance(n, dict) and n.get("type") == "password_entry"
                and n.get("label") == label and n.get("url") == url)
    ]
    if len(new_notes) == len(notes):
        return False
    memory["notes"] = new_notes
    if not os.path.exists("data"):
        os.makedirs("data")
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)
    return True


def add_web_link(name: str, url: str, max_entries: int = 200) -> None:
    """Adds a named web link to memory."""
    name = (name or "").strip()
    url = (url or "").strip()
    if not name or not url:
        return
    memory = load_memory()
    notes = memory.get("notes", [])
    notes.append({
        "type": "web_link",
        "name": name,
        "url": url,
    })
    memory["notes"] = notes[-max_entries:]

    if not os.path.exists("data"):
        os.makedirs("data")
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)


def list_web_links() -> list:
    """Returns all stored web links."""
    memory = load_memory()
    notes = memory.get("notes", [])
    return [
        n for n in notes
        if isinstance(n, dict) and n.get("type") == "web_link" and n.get("name") and n.get("url")
    ]


def remove_web_link(name: str, url: str) -> bool:
    """Remove a web link by name+url."""
    name = (name or "").strip()
    url = (url or "").strip()
    if not name or not url:
        return False
    memory = load_memory()
    notes = memory.get("notes", [])
    new_notes = [
        n for n in notes
        if not (isinstance(n, dict) and n.get("type") == "web_link" and n.get("name") == name and n.get("url") == url)
    ]
    if len(new_notes) == len(notes):
        return False
    memory["notes"] = new_notes
    if not os.path.exists("data"):
        os.makedirs("data")
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)
    return True


def find_web_link(name: str) -> dict | None:
    """Find a web link by name (case-insensitive)."""
    name = (name or "").strip().lower()
    if not name:
        return None
    for entry in list_web_links():
        if str(entry.get("name", "")).strip().lower() == name:
            return entry
    return None


def find_password_entry(label: str | None = None, url: str | None = None) -> dict | None:
    """Find a password entry by label and/or url."""
    label = (label or "").strip()
    url = (url or "").strip()
    entries = list_password_entries()
    if label and url:
        for entry in entries:
            if entry.get("label") == label and entry.get("url") == url:
                return entry
    if label:
        for entry in entries:
            if entry.get("label") == label:
                return entry
    if url:
        for entry in entries:
            if entry.get("url") == url:
                return entry
    return None