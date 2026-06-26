import json
import os
import time
from typing import Any


class ReflectionLogger:
    def __init__(self, file_path: str = os.path.join("data", "task_reflections.jsonl")) -> None:
        self.file_path = file_path
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def log(
        self,
        goal: str,
        page_states: list[str],
        selector_used: dict[str, Any] | None,
        failure: dict[str, Any] | None,
        remember_next: dict[str, Any] | None,
        status: str,
    ) -> dict[str, Any]:
        record = {
            "timestamp": time.time(),
            "goal": goal,
            "status": status,
            "page_states": page_states,
            "selector_used": selector_used or {},
            "failure": failure or {},
            "remember_next": remember_next or {},
        }
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def build_reflection(
        self,
        goal: str,
        observed_states: list[str],
        successful_selector: dict[str, Any] | None,
        failure_details: dict[str, Any] | None,
        memory_recommendation: dict[str, Any] | None,
        status: str,
    ) -> dict[str, Any]:
        return self.log(
            goal=goal,
            page_states=observed_states,
            selector_used=successful_selector,
            failure=failure_details,
            remember_next=memory_recommendation,
            status=status,
        )
