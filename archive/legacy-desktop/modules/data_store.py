import json
import os
from typing import Dict, List, Optional, Tuple

try:
    import openpyxl
except Exception:
    openpyxl = None

DATA_FILE = os.path.join("data", "agent_data.json")


def _load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"active": None, "datasets": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"active": None, "datasets": {}}


def _save_data(data: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def list_datasets() -> List[str]:
    data = _load_data()
    return sorted(list(data.get("datasets", {}).keys()))


def get_active_dataset() -> Optional[str]:
    data = _load_data()
    return data.get("active")


def set_active_dataset(name: str) -> bool:
    name = (name or "").strip()
    data = _load_data()
    if name not in data.get("datasets", {}):
        return False
    data["active"] = name
    _save_data(data)
    return True


def remove_dataset(name: str) -> bool:
    name = (name or "").strip()
    if not name:
        return False
    data = _load_data()
    datasets = data.get("datasets", {})
    if name not in datasets:
        return False
    datasets.pop(name, None)
    if data.get("active") == name:
        data["active"] = None
    data["datasets"] = datasets
    _save_data(data)
    return True


def ingest_excel(file_path: str, dataset_name: Optional[str] = None) -> Tuple[bool, str]:
    if openpyxl is None:
        return False, "openpyxl is not installed."
    file_path = (file_path or "").strip()
    if not file_path or not os.path.isfile(file_path):
        return False, "File not found."

    name = (dataset_name or "").strip()
    if not name:
        base = os.path.basename(file_path)
        name = os.path.splitext(base)[0]

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return False, "Sheet is empty."
        headers = [str(h or "").strip().lower() for h in rows[0]]
        records = []
        for row in rows[1:]:
            rec = {}
            for idx, val in enumerate(row):
                if idx >= len(headers):
                    continue
                key = headers[idx]
                if not key:
                    continue
                rec[key] = "" if val is None else str(val).strip()
            if rec:
                records.append(rec)
        data = _load_data()
        datasets = data.get("datasets", {})
        datasets[name] = {
            "source": file_path,
            "records": records,
        }
        data["datasets"] = datasets
        if not data.get("active"):
            data["active"] = name
        _save_data(data)
        return True, f"Loaded {len(records)} rows into '{name}'."
    except Exception as e:
        return False, f"Failed to read Excel: {type(e).__name__}: {e}"


def _normalize(value: str) -> str:
    return (value or "").strip().lower()


def _find_record_by_column(records: List[dict], column: str, value: str) -> Optional[dict]:
    col = _normalize(column)
    target = _normalize(value)
    for rec in records:
        if _normalize(rec.get(col, "")) == target:
            return rec
    return None


def lookup_writing_agent(name: str) -> Optional[dict]:
    data = _load_data()
    active = data.get("active")
    if not active:
        return None
    dataset = data.get("datasets", {}).get(active)
    if not dataset:
        return None
    records = dataset.get("records", [])
    if not records:
        return None

    possible_cols = ["writing agent", "writing_agent", "agent", "producer", "writer"]
    for col in possible_cols:
        found = _find_record_by_column(records, col, name)
        if found:
            return found
    return None


def extract_agent_fields(record: dict) -> dict:
    if not record:
        return {}
    def pick(keys: List[str]) -> str:
        for k in keys:
            v = record.get(k)
            if v:
                return str(v)
        return ""

    return {
        "first_name": pick(["first name", "firstname", "first"]),
        "last_name": pick(["last name", "lastname", "last"]),
        "npn": pick(["npn#", "npn", "npn number", "npn_number"]),
    }
