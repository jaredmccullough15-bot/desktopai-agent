from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Optional

from models import (
    ConfidenceUpdateIn,
    FailureAnalysisIn,
    MachineOverride,
    RunResultIn,
    SelectorRecord,
    TaskQueueCompleteIn,
    TaskQueueSubmitIn,
    WorkflowRecord,
    WorkflowStep,
)


class WorkflowStore:
    def __init__(self, db_path: str = os.path.join("data", "shared_memory_hub.db")) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS site_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'global',
                    machine_id TEXT NOT NULL DEFAULT '',
                    workflow_version INTEGER NOT NULL DEFAULT 1,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    trusted INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(site, task_type, scope, machine_id, workflow_version)
                );

                CREATE TABLE IF NOT EXISTS workflow_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'global',
                    machine_id TEXT NOT NULL DEFAULT '',
                    workflow_version INTEGER NOT NULL,
                    step_order INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    selector_type TEXT NOT NULL,
                    selector_value TEXT NOT NULL,
                    wait_condition TEXT,
                    fallback_hint TEXT,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS selector_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    selector_type TEXT NOT NULL,
                    selector_value TEXT NOT NULL,
                    wait_condition TEXT,
                    fallback_method TEXT,
                    scope TEXT NOT NULL DEFAULT 'global',
                    machine_id TEXT NOT NULL DEFAULT '',
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    trusted INTEGER NOT NULL DEFAULT 0,
                    last_success_ts REAL,
                    last_failure_ts REAL,
                    UNIQUE(site, task_type, action_name, selector_type, selector_value, scope, machine_id)
                );

                CREATE TABLE IF NOT EXISTS run_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    machine_id TEXT NOT NULL,
                    site TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    workflow_version INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    selector_used_json TEXT,
                    fallback_path_json TEXT,
                    screenshot_path TEXT,
                    url TEXT,
                    title TEXT,
                    notes_json TEXT
                );

                CREATE TABLE IF NOT EXISTS failure_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    machine_id TEXT NOT NULL,
                    site TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    failure_type TEXT NOT NULL,
                    error_text TEXT,
                    screenshot_path TEXT,
                    url TEXT,
                    title TEXT,
                    dom_excerpt TEXT,
                    selector_attempts_json TEXT,
                    fallback_path_json TEXT
                );

                CREATE TABLE IF NOT EXISTS machine_profiles (
                    machine_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    capabilities_json TEXT,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS machine_overrides (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_id TEXT NOT NULL,
                    site TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(machine_id, site, task_type, key)
                );

                CREATE TABLE IF NOT EXISTS task_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    machine_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    claimed_at REAL,
                    completed_at REAL
                );
                """
            )

    @staticmethod
    def _confidence(success_count: int, failure_count: int) -> tuple[float, int]:
        total = max(1, success_count + failure_count)
        confidence = round(success_count / total, 4)
        trusted = 1 if success_count >= 3 and confidence >= 0.75 else 0
        return confidence, trusted

    def upsert_workflow(self, workflow: WorkflowRecord) -> None:
        now = time.time()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT success_count, failure_count FROM site_profiles
                WHERE site=? AND task_type=? AND scope=? AND machine_id=? AND workflow_version=?
                """,
                (workflow.site, workflow.task_type, workflow.scope, workflow.machine_id, workflow.version),
            ).fetchone()

            success_count = int(existing["success_count"]) if existing else 0
            failure_count = int(existing["failure_count"]) if existing else 0
            confidence, trusted = self._confidence(success_count, failure_count)

            if existing:
                conn.execute(
                    """
                    UPDATE site_profiles
                    SET confidence=?, trusted=?, updated_at=?
                    WHERE site=? AND task_type=? AND scope=? AND machine_id=? AND workflow_version=?
                    """,
                    (confidence, trusted, now, workflow.site, workflow.task_type, workflow.scope, workflow.machine_id, workflow.version),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO site_profiles (
                        site, task_type, scope, machine_id, workflow_version,
                        confidence, trusted, success_count, failure_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workflow.site,
                        workflow.task_type,
                        workflow.scope,
                        workflow.machine_id,
                        workflow.version,
                        confidence,
                        trusted,
                        success_count,
                        failure_count,
                        now,
                        now,
                    ),
                )

            conn.execute(
                """
                DELETE FROM workflow_steps
                WHERE site=? AND task_type=? AND scope=? AND machine_id=? AND workflow_version=?
                """,
                (workflow.site, workflow.task_type, workflow.scope, workflow.machine_id, workflow.version),
            )

            for step in workflow.steps:
                conn.execute(
                    """
                    INSERT INTO workflow_steps (
                        site, task_type, scope, machine_id, workflow_version,
                        step_order, action_type, selector_type, selector_value,
                        wait_condition, fallback_hint, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workflow.site,
                        workflow.task_type,
                        workflow.scope,
                        workflow.machine_id,
                        workflow.version,
                        step.step_order,
                        step.action_type,
                        step.selector_type,
                        step.selector_value,
                        step.wait_condition,
                        step.fallback_hint,
                        now,
                    ),
                )

    def get_workflow(self, site: str, task_type: str, machine_id: str = "") -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            machine_row = conn.execute(
                """
                SELECT * FROM site_profiles
                WHERE site=? AND task_type=? AND scope='machine' AND machine_id=?
                ORDER BY trusted DESC, confidence DESC, success_count DESC, workflow_version DESC
                LIMIT 1
                """,
                (site, task_type, machine_id),
            ).fetchone()

            global_row = conn.execute(
                """
                SELECT * FROM site_profiles
                WHERE site=? AND task_type=? AND scope='global'
                ORDER BY trusted DESC, confidence DESC, success_count DESC, workflow_version DESC
                LIMIT 1
                """,
                (site, task_type),
            ).fetchone()

            row = machine_row or global_row
            if not row:
                return None

            steps = conn.execute(
                """
                SELECT step_order, action_type, selector_type, selector_value, wait_condition, fallback_hint
                FROM workflow_steps
                WHERE site=? AND task_type=? AND scope=? AND machine_id=? AND workflow_version=?
                ORDER BY step_order ASC
                """,
                (row["site"], row["task_type"], row["scope"], row["machine_id"], row["workflow_version"]),
            ).fetchall()

            return {
                "site": row["site"],
                "task_type": row["task_type"],
                "scope": row["scope"],
                "machine_id": row["machine_id"],
                "workflow_version": row["workflow_version"],
                "confidence": row["confidence"],
                "trusted": bool(row["trusted"]),
                "success_count": row["success_count"],
                "failure_count": row["failure_count"],
                "steps": [dict(s) for s in steps],
            }

    def get_selector_memory(self, site: str, task_type: str, machine_id: str = "", limit: int = 25) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM selector_memory
                WHERE site=? AND task_type=? AND (scope='global' OR (scope='machine' AND machine_id=?))
                ORDER BY (scope='machine') DESC, trusted DESC, confidence DESC, success_count DESC
                LIMIT ?
                """,
                (site, task_type, machine_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def upsert_selector_memory(self, row: SelectorRecord, success: bool) -> None:
        now = time.time()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM selector_memory
                WHERE site=? AND task_type=? AND action_name=? AND selector_type=? AND selector_value=?
                AND scope=? AND machine_id=?
                """,
                (
                    row.site,
                    row.task_type,
                    row.action_name,
                    row.selector_type,
                    row.selector_value,
                    row.scope,
                    row.machine_id,
                ),
            ).fetchone()

            if existing:
                success_count = int(existing["success_count"]) + (1 if success else 0)
                failure_count = int(existing["failure_count"]) + (0 if success else 1)
                confidence, trusted = self._confidence(success_count, failure_count)
                conn.execute(
                    """
                    UPDATE selector_memory
                    SET wait_condition=?, fallback_method=?, success_count=?, failure_count=?,
                        confidence=?, trusted=?, last_success_ts=?, last_failure_ts=?
                    WHERE id=?
                    """,
                    (
                        row.wait_condition,
                        row.fallback_method,
                        success_count,
                        failure_count,
                        confidence,
                        trusted,
                        now if success else existing["last_success_ts"],
                        now if not success else existing["last_failure_ts"],
                        existing["id"],
                    ),
                )
            else:
                success_count = 1 if success else 0
                failure_count = 0 if success else 1
                confidence, trusted = self._confidence(success_count, failure_count)
                conn.execute(
                    """
                    INSERT INTO selector_memory (
                        site, task_type, action_name, selector_type, selector_value,
                        wait_condition, fallback_method, scope, machine_id,
                        success_count, failure_count, confidence, trusted,
                        last_success_ts, last_failure_ts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.site,
                        row.task_type,
                        row.action_name,
                        row.selector_type,
                        row.selector_value,
                        row.wait_condition,
                        row.fallback_method,
                        row.scope,
                        row.machine_id,
                        success_count,
                        failure_count,
                        confidence,
                        trusted,
                        now if success else None,
                        now if not success else None,
                    ),
                )

    def submit_run_result(self, run: RunResultIn) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO run_history (
                    timestamp, machine_id, site, task_type, workflow_version, success,
                    selector_used_json, fallback_path_json, screenshot_path, url, title, notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    run.machine_id,
                    run.site,
                    run.task_type,
                    run.workflow_version,
                    1 if run.success else 0,
                    json.dumps(run.selector_used or {}),
                    json.dumps(run.fallback_path or []),
                    run.screenshot_path,
                    run.url,
                    run.title,
                    json.dumps(run.notes or {}),
                ),
            )

        self.update_confidence(
            ConfidenceUpdateIn(
                site=run.site,
                task_type=run.task_type,
                scope="machine",
                machine_id=run.machine_id,
                version=run.workflow_version,
                success_delta=1 if run.success else 0,
                failure_delta=0 if run.success else 1,
            )
        )

    def submit_failure_analysis(self, failure: FailureAnalysisIn) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO failure_analysis (
                    timestamp, machine_id, site, task_type, failure_type, error_text,
                    screenshot_path, url, title, dom_excerpt, selector_attempts_json, fallback_path_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    failure.machine_id,
                    failure.site,
                    failure.task_type,
                    failure.failure_type,
                    failure.error_text,
                    failure.screenshot_path,
                    failure.url,
                    failure.title,
                    failure.dom_excerpt,
                    json.dumps(failure.selector_attempts or []),
                    json.dumps(failure.fallback_path or []),
                ),
            )

    def get_machine_overrides(self, machine_id: str, site: str = "", task_type: str = "") -> list[dict[str, Any]]:
        where = ["machine_id=?"]
        args: list[Any] = [machine_id]
        if site:
            where.append("site=?")
            args.append(site)
        if task_type:
            where.append("task_type=?")
            args.append(task_type)

        query = f"SELECT * FROM machine_overrides WHERE {' AND '.join(where)} ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(args)).fetchall()
            result = []
            for r in rows:
                row = dict(r)
                row["value_json"] = json.loads(row.get("value_json") or "{}")
                result.append(row)
            return result

    def upsert_machine_override(self, override: MachineOverride) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO machine_overrides (machine_id, site, task_type, key, value_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(machine_id, site, task_type, key)
                DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
                """,
                (
                    override.machine_id,
                    override.site,
                    override.task_type,
                    override.key,
                    json.dumps(override.value_json or {}),
                    now,
                ),
            )

    def update_confidence(self, request: ConfidenceUpdateIn) -> None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM site_profiles
                WHERE site=? AND task_type=? AND scope=? AND machine_id=?
                AND (? IS NULL OR workflow_version=?)
                ORDER BY workflow_version DESC LIMIT 1
                """,
                (
                    request.site,
                    request.task_type,
                    request.scope,
                    request.machine_id,
                    request.version,
                    request.version,
                ),
            ).fetchone()

            if not row:
                return

            success_count = int(row["success_count"]) + int(request.success_delta or 0)
            failure_count = int(row["failure_count"]) + int(request.failure_delta or 0)
            confidence, trusted = self._confidence(success_count, failure_count)

            conn.execute(
                """
                UPDATE site_profiles
                SET success_count=?, failure_count=?, confidence=?, trusted=?, updated_at=?
                WHERE id=?
                """,
                (success_count, failure_count, confidence, trusted, time.time(), row["id"]),
            )

    def enqueue_task(self, task: TaskQueueSubmitIn) -> int:
        now = time.time()
        payload = {
            "machine_id": task.machine_id,
            "site": task.site,
            "task_type": task.task_type,
            "start_url": task.start_url,
            "goal": task.goal,
            "input_data": task.input_data or {},
        }
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO task_queue (created_at, updated_at, machine_id, status, payload_json)
                VALUES (?, ?, ?, 'queued', ?)
                """,
                (now, now, task.machine_id, json.dumps(payload)),
            )
            return int(cur.lastrowid)

    def claim_next_task(self, machine_id: str) -> dict[str, Any] | None:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM task_queue
                WHERE machine_id=? AND status='queued'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (machine_id,),
            ).fetchone()
            if not row:
                return None

            conn.execute(
                """
                UPDATE task_queue
                SET status='claimed', updated_at=?, claimed_at=?
                WHERE id=?
                """,
                (now, now, row["id"]),
            )

            payload = json.loads(row["payload_json"] or "{}")
            payload["task_id"] = int(row["id"])
            return payload

    def complete_task(self, task_id: int, completion: TaskQueueCompleteIn) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE task_queue
                SET status=?, updated_at=?, completed_at=?, result_json=?
                WHERE id=? AND machine_id=?
                """,
                (
                    "done" if completion.success else "failed",
                    now,
                    now,
                    json.dumps(completion.result_json or {}),
                    int(task_id),
                    completion.machine_id,
                ),
            )

    def get_task_status(self, machine_id: str = "", limit: int = 25) -> dict[str, Any]:
        with self._connect() as conn:
            status_rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM task_queue
                WHERE (?='' OR machine_id=?)
                GROUP BY status
                """,
                (machine_id, machine_id),
            ).fetchall()

            counts = {"queued": 0, "claimed": 0, "done": 0, "failed": 0}
            for row in status_rows:
                status = str(row["status"] or "")
                counts[status] = int(row["count"])

            recent_rows = conn.execute(
                """
                SELECT id, machine_id, status, created_at, claimed_at, completed_at, payload_json
                FROM task_queue
                WHERE (?='' OR machine_id=?)
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (machine_id, machine_id, max(1, int(limit))),
            ).fetchall()

            recent: list[dict[str, Any]] = []
            for row in recent_rows:
                payload = json.loads(row["payload_json"] or "{}")
                recent.append(
                    {
                        "task_id": int(row["id"]),
                        "machine_id": row["machine_id"],
                        "status": row["status"],
                        "site": payload.get("site", ""),
                        "task_type": payload.get("task_type", ""),
                        "goal": payload.get("goal", ""),
                        "created_at": float(row["created_at"] or 0),
                        "claimed_at": float(row["claimed_at"] or 0) if row["claimed_at"] else None,
                        "completed_at": float(row["completed_at"] or 0) if row["completed_at"] else None,
                    }
                )

            return {"counts": counts, "recent": recent}
