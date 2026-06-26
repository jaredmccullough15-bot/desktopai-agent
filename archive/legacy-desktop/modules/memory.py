import json
import os
import re
import time

MEMORY_FILE = "data/desktop_memory.json"

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "of", "on", "or", "that", "the", "to", "was", "were", "with",
    "this", "these", "those", "when", "then", "into", "than", "not", "no"
}

_PATTERN_GROUPS = {
    "element_interaction": "ui_interaction",
    "pagination_navigation": "navigation",
    "navigation": "navigation",
    "search_refinement": "search",
    "form_filling": "form",
    "healthsherpa_ssn_panel_assist": "healthsherpa",
    "healthsherpa_id_button_assist": "healthsherpa",
    "general": "general",
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _tokenize(value: str) -> set[str]:
    text = _normalize_text(value)
    parts = re.split(r"[^a-z0-9]+", text)
    return {p for p in parts if p and p not in _STOPWORDS and len(p) >= 2}


def _pattern_group(pattern_type: str) -> str:
    pt = _normalize_text(pattern_type)
    return _PATTERN_GROUPS.get(pt, pt or "general")

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


# ========== ADAPTIVE LEARNING SYSTEM ==========

def add_learning_pattern(pattern_type: str, context: str, solution: str, success_count: int = 1) -> None:
    """
    Store a successful problem-solving pattern that AI can apply in similar situations.
    
    Args:
        pattern_type: Category of pattern (e.g., "element_interaction", "navigation", "data_extraction")
        context: Description of when this pattern applies (e.g., "element not found in viewport")
        solution: What to do (e.g., "scroll_to_bottom_before_search")
        success_count: Number of times this pattern has been successfully applied
    """
    memory = load_memory()
    patterns = memory.get("learning_patterns", [])
    now_ts = time.time()
    source_procedure = str(os.getenv("CURRENT_PROCEDURE_NAME", "") or "").strip()
    
    # Check if pattern already exists, increment success count
    for pattern in patterns:
        if (pattern.get("pattern_type") == pattern_type and 
            pattern.get("context") == context and 
            pattern.get("solution") == solution):
            pattern["success_count"] = pattern.get("success_count", 1) + success_count
            pattern["last_used"] = now_ts
            if source_procedure:
                pattern["source_procedure"] = source_procedure
            pattern["pattern_group"] = _pattern_group(pattern_type)
            break
    else:
        # Add new pattern
        patterns.append({
            "pattern_type": pattern_type,
            "context": context,
            "solution": solution,
            "success_count": success_count,
            "learned_at": now_ts,
            "last_used": now_ts,
            "source_procedure": source_procedure,
            "pattern_group": _pattern_group(pattern_type),
        })
    
    memory["learning_patterns"] = patterns[-100:]  # Keep last 100 patterns
    
    if not os.path.exists("data"):
        os.makedirs("data")
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)
    print(f"🧠 Learned pattern: {pattern_type} → {solution}")
    
    # Sync to cloud if enabled
    try:
        from .sync import get_sync_instance
        sync = get_sync_instance()
        if sync.enabled:
            sync.push_patterns_to_cloud()
    except Exception:
        pass  # Sync is optional, don't fail if unavailable



def get_learning_patterns(pattern_type: str = None, min_success: int = 1) -> list:
    """
    Retrieve learned patterns, optionally filtered by type and success threshold.
    
    Args:
        pattern_type: Filter by specific pattern type (None = all patterns)
        min_success: Minimum success count threshold
    
    Returns:
        List of patterns sorted by success count (most successful first)
    """
    memory = load_memory()
    patterns = memory.get("learning_patterns", [])
    
    # Filter by type if specified
    if pattern_type:
        patterns = [p for p in patterns if p.get("pattern_type") == pattern_type]
    
    # Filter by minimum success count
    patterns = [p for p in patterns if p.get("success_count", 0) >= min_success]
    
    # Sort by success count (descending)
    patterns.sort(key=lambda p: p.get("success_count", 0), reverse=True)
    
    return patterns


def should_apply_pattern(pattern_type: str, context_keywords: list) -> dict | None:
    """
    Check if a learned pattern should be applied based on context.
    
    Args:
        pattern_type: Type of pattern to look for
        context_keywords: List of keywords describing current situation
    
    Returns:
        Best matching pattern dict or None
    """
    query_type = _normalize_text(pattern_type)
    query_group = _pattern_group(query_type)
    current_procedure = str(os.getenv("CURRENT_PROCEDURE_NAME", "") or "").strip()

    raw_keywords = context_keywords or []
    keyword_text = " ".join([str(k or "") for k in raw_keywords])
    query_tokens = _tokenize(keyword_text)

    all_patterns = get_learning_patterns(pattern_type=None)
    if not all_patterns:
        return None

    best_pattern = None
    best_score = 0.0

    for pattern in all_patterns:
        ptype = _normalize_text(pattern.get("pattern_type", ""))
        pgroup = _pattern_group(ptype)
        pcontext = _normalize_text(pattern.get("context", ""))
        psolution = _normalize_text(pattern.get("solution", ""))
        success_count = int(pattern.get("success_count", 0) or 0)

        type_score = 0.0
        if ptype == query_type:
            type_score = 0.45
        elif pgroup == query_group:
            type_score = 0.30
        elif pgroup in {"general", "ui_interaction", "navigation"}:
            type_score = 0.15

        context_score = 0.0
        if query_tokens:
            p_tokens = _tokenize(pcontext + " " + psolution)
            overlap = len(query_tokens.intersection(p_tokens))
            context_score = overlap / max(1, len(query_tokens))
        else:
            lowered_keywords = [_normalize_text(k) for k in raw_keywords if str(k or "").strip()]
            if any(k and (k in pcontext or k in psolution) for k in lowered_keywords):
                context_score = 0.5

        success_score = min(0.25, success_count / 20.0)

        transfer_bonus = 0.0
        source_proc = str(pattern.get("source_procedure", "") or "").strip()
        if current_procedure and source_proc and (current_procedure != source_proc):
            transfer_bonus = 0.05

        total_score = type_score + context_score + success_score + transfer_bonus
        if total_score > best_score:
            best_score = total_score
            best_pattern = pattern

    # Require a minimum confidence to avoid bad cross-procedure guesses.
    if best_pattern is None or best_score < 0.35:
        return None

    # Touch last_used for adaptive ranking.
    memory = load_memory()
    patterns = memory.get("learning_patterns", [])
    for pattern in patterns:
        if (
            pattern.get("pattern_type") == best_pattern.get("pattern_type")
            and pattern.get("context") == best_pattern.get("context")
            and pattern.get("solution") == best_pattern.get("solution")
        ):
            pattern["last_used"] = time.time()
            break
    memory["learning_patterns"] = patterns
    if not os.path.exists("data"):
        os.makedirs("data")
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)

    return best_pattern