from __future__ import annotations

import json
import os
import platform
import time
from datetime import datetime
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from browser_controller import BrowserController
from models import TaskRequest
from reflection_logger import ReflectionLogger


class LocalWorkerService:
    def __init__(
        self,
        memory_api_base: str,
        machine_id: str | None = None,
        poll_interval_sec: float = 2.0,
        task_file: str | None = None,
    ) -> None:
        self.memory_api_base = memory_api_base.rstrip("/")
        self.machine_id = machine_id or self._default_machine_id()
        self.poll_interval_sec = poll_interval_sec
        self.task_file = task_file or os.path.join("data", f"worker_tasks_{self.machine_id}.jsonl")
        self.browser = BrowserController(headless=False)
        self.reflection = ReflectionLogger(os.path.join("data", f"worker_reflections_{self.machine_id}.jsonl"))
        os.makedirs("data", exist_ok=True)

    @staticmethod
    def _default_machine_id() -> str:
        user = os.getenv("USERNAME") or os.getenv("USER") or "unknown"
        host = platform.node() or "unknown-host"
        return f"{user}@{host}"

    def run_forever(self) -> None:
        print(f"[Worker] machine_id={self.machine_id} status=starting")
        while True:
            task = self._claim_next_task_api()
            if task is None:
                task = self._read_next_task()
            if task is None:
                time.sleep(self.poll_interval_sec)
                continue
            self.execute_task(task)

    def execute_task(self, task: TaskRequest | dict[str, Any]) -> dict[str, Any]:
        task_id = None
        raw_task = task if isinstance(task, dict) else task.model_dump()
        if isinstance(raw_task, dict):
            task_id = raw_task.pop("task_id", None)
        payload = TaskRequest(**raw_task) if isinstance(raw_task, dict) else task
        input_data = dict(payload.input_data or {})

        retry_attempts = 0
        try:
            retry_attempts = max(0, min(8, int(input_data.get("retry_attempts", 0))))
        except Exception:
            retry_attempts = 0

        wait_times = input_data.get("wait_times") if isinstance(input_data.get("wait_times"), dict) else {}
        retry_delays_ms = wait_times.get("retry_delays_ms") if isinstance(wait_times.get("retry_delays_ms"), list) else []
        selector_strategy = str(input_data.get("selector_strategy") or "balanced")
        workflow_variation = str(input_data.get("workflow_variation") or "")
        debug_outputs = input_data.get("debug_outputs") if isinstance(input_data.get("debug_outputs"), dict) else {}

        workflow = self._api_get(
            "/workflow",
            {
                "site": payload.site,
                "task_type": payload.task_type,
                "machine_id": self.machine_id,
            },
            allow_not_found=True,
        )
        selectors = self._api_get(
            "/selectors",
            {
                "site": payload.site,
                "task_type": payload.task_type,
                "machine_id": self.machine_id,
            },
            allow_not_found=True,
        )
        overrides = self._api_get(
            f"/machine-overrides/{urllib.parse.quote(self.machine_id, safe='')}",
            {
                "site": payload.site,
                "task_type": payload.task_type,
            },
            allow_not_found=True,
        )

        workflow_steps = (workflow or {}).get("steps", [])
        workflow_version = int((workflow or {}).get("workflow_version", 1))

        if not workflow_steps:
            workflow_steps = payload.input_data.get("workflow_steps", [])

        print(
            f"[Worker] machine_id={self.machine_id} site={payload.site} task_type={payload.task_type} "
            f"selected_workflow_version={workflow_version} selectors_from_memory={len((selectors or {}).get('selectors', []))}"
        )

        execution_feedback: list[dict[str, Any]] = []
        result: dict[str, Any] | None = None
        last_error: Exception | None = None
        max_attempts = retry_attempts + 1
        for attempt in range(1, max_attempts + 1):
            started_at = datetime.utcnow().isoformat()
            try:
                result = self.browser.execute_workflow(
                    start_url=payload.start_url,
                    workflow_steps=workflow_steps,
                    machine_id=self.machine_id,
                    site=payload.site,
                    task_type=payload.task_type,
                )
                execution_feedback.append(
                    {
                        "step_name": f"task:{payload.task_type}",
                        "success": True,
                        "reason": "attempt_completed",
                        "retries_attempted": attempt - 1,
                        "started_at": started_at,
                        "finished_at": datetime.utcnow().isoformat(),
                        "attempt": attempt,
                    }
                )
                break
            except Exception as error:
                last_error = error
                execution_feedback.append(
                    {
                        "step_name": f"task:{payload.task_type}",
                        "success": False,
                        "reason": str(error),
                        "retries_attempted": attempt - 1,
                        "started_at": started_at,
                        "finished_at": datetime.utcnow().isoformat(),
                        "attempt": attempt,
                    }
                )
                if attempt < max_attempts:
                    delay_ms = 0
                    if attempt - 1 < len(retry_delays_ms):
                        try:
                            delay_ms = max(0, min(120000, int(retry_delays_ms[attempt - 1])))
                        except Exception:
                            delay_ms = 0
                    if delay_ms > 0:
                        time.sleep(delay_ms / 1000.0)

        if result is None:
            if last_error:
                raise last_error
            raise RuntimeError("Task failed without explicit error")

        result["adaptive_execution"] = {
            "retry_attempts": retry_attempts,
            "wait_times": wait_times,
            "selector_strategy": selector_strategy,
            "workflow_variation": workflow_variation,
            "debug_outputs": debug_outputs,
        }
        result["execution_feedback"] = execution_feedback

        selector_used = {}
        if result.get("selector_outcomes"):
            for row in result["selector_outcomes"]:
                if row.get("success"):
                    selector_used = {
                        "selector_type": row.get("selector_type", ""),
                        "selector_value": row.get("selector_value", ""),
                        "action_name": row.get("action_name", ""),
                    }
                    break

        run_result_payload = {
            "machine_id": self.machine_id,
            "site": payload.site,
            "task_type": payload.task_type,
            "workflow_version": workflow_version,
            "success": bool(result.get("success")),
            "selector_used": selector_used,
            "fallback_path": result.get("fallback_path", []),
            "screenshot_path": (result.get("failure") or {}).get("screenshot_path", ""),
            "url": result.get("url") or (result.get("failure") or {}).get("url", ""),
            "title": result.get("title") or (result.get("failure") or {}).get("title", ""),
            "notes": {"override_count": len((overrides or {}).get("overrides", []))},
        }
        self._api_post("/run-result", run_result_payload)

        if task_id is not None:
            self._api_post(
                f"/tasks/{int(task_id)}/complete",
                {
                    "machine_id": self.machine_id,
                    "success": bool(result.get("success")),
                    "result_json": result,
                },
            )

        for so in result.get("selector_outcomes", []):
            selector_payload = {
                "site": payload.site,
                "task_type": payload.task_type,
                "action_name": so.get("action_name", ""),
                "selector_type": so.get("selector_type", ""),
                "selector_value": so.get("selector_value", ""),
                "wait_condition": so.get("wait_condition", "visible"),
                "fallback_method": " -> ".join(result.get("fallback_path", [])),
                "scope": "machine",
                "machine_id": self.machine_id,
            }
            self._api_post(f"/selectors/outcome?success={'true' if so.get('success') else 'false'}", selector_payload)

        if not result.get("success") and result.get("failure"):
            failure = result["failure"]
            failure_payload = {
                "machine_id": self.machine_id,
                "site": payload.site,
                "task_type": payload.task_type,
                "failure_type": failure.get("failure_type", "element not found"),
                "error_text": failure.get("error_text", ""),
                "screenshot_path": failure.get("screenshot_path", ""),
                "url": failure.get("url", ""),
                "title": failure.get("title", ""),
                "dom_excerpt": failure.get("dom_excerpt", ""),
                "selector_attempts": [
                    {
                        "selector_type": s.get("selector_type", ""),
                        "selector_value": s.get("selector_value", ""),
                    }
                    for s in result.get("selector_outcomes", [])
                ],
                "fallback_path": result.get("fallback_path", []),
            }
            self._api_post("/failure-analysis", failure_payload)

        self.reflection.log(
            machine_id=self.machine_id,
            site=payload.site,
            task_type=payload.task_type,
            goal=payload.goal,
            workflow_version=workflow_version,
            selector_used=selector_used,
            fallback_path=result.get("fallback_path", []),
            success=bool(result.get("success")),
            failure_type=(result.get("failure") or {}).get("failure_type", ""),
            notes={"workflow_steps": len(workflow_steps)},
        )

        print(
            f"[Worker] machine_id={self.machine_id} site={payload.site} task_type={payload.task_type} "
            f"workflow_version={workflow_version} selector_used={selector_used} "
            f"fallback_path={result.get('fallback_path', [])} success={result.get('success')} "
            f"screenshot={(result.get('failure') or {}).get('screenshot_path', '')}"
        )
        return result

    def _api_get(self, path: str, query: dict[str, Any], allow_not_found: bool = False) -> dict[str, Any] | None:
        qs = urllib.parse.urlencode(query)
        url = f"{self.memory_api_base}{path}?{qs}" if qs else f"{self.memory_api_base}{path}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if allow_not_found and exc.code == 404:
                return None
            raise

    def _api_post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.memory_api_base}{path}"
        req = urllib.request.Request(
            url,
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(body).encode("utf-8"),
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _read_next_task(self) -> dict[str, Any] | None:
        if not os.path.exists(self.task_file):
            return None

        with open(self.task_file, "r", encoding="utf-8") as f:
            lines = [ln for ln in f.readlines() if ln.strip()]
        if not lines:
            return None

        task_line = lines[0]
        remaining = lines[1:]
        with open(self.task_file, "w", encoding="utf-8") as f:
            f.writelines(remaining)

        return json.loads(task_line)

    def _claim_next_task_api(self) -> dict[str, Any] | None:
        try:
            payload = self._api_get("/tasks/next", {"machine_id": self.machine_id}, allow_not_found=False)
            task = (payload or {}).get("task")
            return task if isinstance(task, dict) else None
        except Exception:
            return None


def example_task_flow() -> None:
    """Example flow: worker pulls shared memory before run and writes back outcomes."""
    worker = LocalWorkerService(memory_api_base=os.getenv("JARVIS_MEMORY_API", "http://127.0.0.1:8787"))
    sample_task = {
        "machine_id": worker.machine_id,
        "site": "example.com",
        "task_type": "open_more_info",
        "start_url": "https://example.com",
        "goal": "Open More information link",
        "input_data": {
            "workflow_steps": [
                {
                    "step_order": 1,
                    "action_type": "click",
                    "selector_type": "role",
                    "selector_value": "link::More information...",
                    "wait_condition": "domcontentloaded",
                    "fallback_hint": "try visible text fallback",
                }
            ]
        },
    }
    worker.execute_task(sample_task)


if __name__ == "__main__":
    mode = os.getenv("JARVIS_WORKER_MODE", "service").strip().lower()
    poll_interval = float((os.getenv("JARVIS_WORKER_POLL_INTERVAL") or "2.0").strip() or "2.0")
    worker = LocalWorkerService(
        memory_api_base=os.getenv("JARVIS_MEMORY_API", "http://127.0.0.1:8787"),
        machine_id=(os.getenv("JARVIS_MACHINE_ID") or "").strip() or None,
        poll_interval_sec=poll_interval,
    )
    if mode == "example":
        example_task_flow()
    else:
        worker.run_forever()
