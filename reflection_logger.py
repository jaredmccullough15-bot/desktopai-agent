from __future__ import annotations

import json
import os
import time
from typing import Any


class ReflectionLogger:
    def __init__(self, path: str = os.path.join("data", "worker_reflections.jsonl")) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def log(
        self,
        machine_id: str,
        site: str,
        task_type: str,
        goal: str,
        workflow_version: int,
        selector_used: dict[str, Any] | None,
        fallback_path: list[str] | None,
        success: bool,
        failure_type: str = "",
        notes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "timestamp": time.time(),
            "machine_id": machine_id,
            "site": site,
            "task_type": task_type,
            "goal": goal,
            "workflow_version": workflow_version,
            "selector_used": selector_used or {},
            "fallback_path": fallback_path or [],
            "success": bool(success),
            "failure_type": failure_type,
            "notes": notes or {},
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
