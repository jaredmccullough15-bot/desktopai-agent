"""bill_chat_service.py — Conversational Command Center Adapter (Phase 9).

Translates natural-language chat messages into Bill Core actions by reusing
existing services (task_service, action_dispatcher, worker registry) as
injectable callables. This keeps the service fully testable without touching
any live runtime state.

Supported intents (rule-based, no LLM):
    start_new_workflow  — starts a teaching session for a named workflow
    start_teach_session — opens the teach browser on the selected worker
    worker_status       — lists online workers and their status
    run_smart_sherpa    — queues a strict batch smart_sherpa_sync task
    rename_worker       — renames a worker by UUID or current name
    conversation        — fallback reply
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field


logger = logging.getLogger("bill_chat_service")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class BillChatRequest(BaseModel):
    tenant_id: str
    user_id: str
    session_id: str
    message: str
    target_machine_uuid: Optional[str] = None


class BillChatResponse(BaseModel):
    reply: str
    intent: str
    action: Optional[str] = None
    task_id: Optional[str] = None
    workflow_id: Optional[str] = None
    draft_id: Optional[str] = None
    session_id: Optional[str] = None
    next_required_input: Optional[str] = None
    teaching_mode: Optional[dict[str, Any]] = None
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

_INTENT_PATTERNS: dict[str, list[str]] = {
    "start_new_workflow": [
        "start a new workflow",
        "start new workflow",
        "create workflow",
        "create a new workflow",
        "create a workflow",
        "new workflow",
        "let's create",
    ],
    "start_teach_session": [
        "teach bill",
        "teach this",
        "start teaching",
        "teach me",
    ],
    "worker_status": [
        "worker status",
        "show workers",
        "who is online",
        "worker list",
    ],
    "run_smart_sherpa": [
        "run smart sherpa",
        "start sherpa sync",
        "smart sherpa",
        "sherpa sync",
    ],
    "rename_worker": [
        "rename worker",
        "change worker name",
        "rename the worker",
    ],
}


def _detect_intent(message: str) -> str:
    lowered = (message or "").lower()
    for intent, phrases in _INTENT_PATTERNS.items():
        if any(phrase in lowered for phrase in phrases):
            return intent
    return "conversation"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _extract_workflow_name(message: str) -> str | None:
    """Extract a workflow name from phrases like 'called X', 'named X', 'workflow X'."""
    lowered = message.lower()
    for kw in ("called ", "named ", "name ", "workflow "):
        idx = lowered.find(kw)
        if idx != -1:
            remainder = message[idx + len(kw):].strip().strip("\"':.,").strip()
            if remainder:
                # Take up to the first stop-word or 40 chars
                stop = re.split(r"\s+(?:on|for|and|to|with)\b", remainder, maxsplit=1)
                candidate = (stop[0] if stop else remainder).strip()
                if candidate:
                    return candidate[:40]
    return None


_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


def _parse_rename_command(
    message: str,
    workers: dict[str, dict],
) -> tuple[str | None, str | None]:
    """Extract (machine_uuid, new_name) from a natural-language rename command.

    Supports patterns like:
      "rename worker BillWorker-PC to NewName"
      "change worker name <uuid> to NewName"
      "rename worker <uuid> to NewName"
    """
    # Find "to <new_name>" — take the last occurrence so "rename X to Y" works
    to_idx = message.lower().rfind(" to ")
    new_name: str | None = None
    search_region = message
    if to_idx != -1:
        new_name = message[to_idx + 4:].strip() or None
        search_region = message[:to_idx]

    # Try UUID match in the search region first (most precise)
    target_uuid: str | None = None
    uuid_match = _UUID_RE.search(search_region)
    if uuid_match:
        target_uuid = uuid_match.group(0).lower()
        # Normalise to the key format stored in workers dict
        for stored_uuid in workers:
            if stored_uuid.lower() == target_uuid:
                target_uuid = stored_uuid
                break
    else:
        # Fall back to name match — scan workers for a current name in the message
        region_lower = search_region.lower()
        for uuid, w in workers.items():
            wname = (w.get("machine_name") or "").strip().lower()
            if wname and wname in region_lower:
                target_uuid = uuid
                break

    return target_uuid, new_name


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class BillChatService:
    """Adapter that routes chat messages to existing Bill Core services.

    Dependencies are injected so the service remains testable without
    importing main.py or touching any live state.

    Args:
        create_task_fn:   Callable matching task_service.create_task_record.
        get_workers_fn:   Callable returning the registered_workers dict snapshot.
        rename_worker_fn: Callable(machine_uuid: str, new_name: str) -> dict.
    """

    def __init__(
        self,
        create_task_fn: Callable[[dict[str, Any]], Any],
        get_workers_fn: Callable[[], dict[str, dict]],
        rename_worker_fn: Callable[[str, str], dict[str, Any]],
        start_teaching_mode_fn: Callable[..., dict[str, Any]],
    ) -> None:
        self._create_task = create_task_fn
        self._get_workers = get_workers_fn
        self._rename_worker = rename_worker_fn
        self._start_teaching_mode = start_teaching_mode_fn

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def handle_message(self, request: BillChatRequest) -> BillChatResponse:
        intent = _detect_intent(request.message)

        if intent == "start_new_workflow":
            return self._handle_start_new_workflow(request)
        if intent == "start_teach_session":
            return self._handle_start_teach_session(request)
        if intent == "worker_status":
            return self._handle_worker_status()
        if intent == "run_smart_sherpa":
            return self._handle_run_smart_sherpa(request)
        if intent == "rename_worker":
            return self._handle_rename_worker(request)

        return BillChatResponse(
            reply="I understand. Tell me what you'd like to do.",
            intent="conversation",
        )

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    def _handle_start_new_workflow(self, request: BillChatRequest) -> BillChatResponse:
        workflow_name = _extract_workflow_name(request.message)
        startup = self._start_teaching_mode(
            endpoint="bill_chat",
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            message=request.message,
            workflow_name=workflow_name,
            target_machine_uuid=request.target_machine_uuid,
            session_context={"session_id": request.session_id},
        )
        teaching_mode = startup.get("teaching_mode")
        if hasattr(teaching_mode, "model_dump"):
            teaching_mode = teaching_mode.model_dump()

        return BillChatResponse(
            reply=str(startup.get("reply") or startup.get("after_execution") or ""),
            intent="start_new_workflow",
            action="task_queued" if startup.get("task_id") else None,
            task_id=startup.get("task_id"),
            workflow_id=startup.get("workflow_id"),
            draft_id=startup.get("draft_id"),
            session_id=startup.get("session_id"),
            next_required_input=startup.get("next_required_input"),
            teaching_mode=teaching_mode,
            metadata={
                "workflow_name": startup.get("workflow_id"),
                "status": startup.get("status"),
            },
        )

    def _handle_start_teach_session(self, request: BillChatRequest) -> BillChatResponse:
        startup = self._start_teaching_mode(
            endpoint="bill_chat",
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            message=request.message,
            workflow_name=_extract_workflow_name(request.message),
            target_machine_uuid=request.target_machine_uuid,
            session_context={"session_id": request.session_id},
        )
        teaching_mode = startup.get("teaching_mode")
        if hasattr(teaching_mode, "model_dump"):
            teaching_mode = teaching_mode.model_dump()

        return BillChatResponse(
            reply=str(startup.get("reply") or startup.get("after_execution") or ""),
            intent="start_teach_session",
            action="task_queued" if startup.get("task_id") else None,
            task_id=startup.get("task_id"),
            workflow_id=startup.get("workflow_id"),
            draft_id=startup.get("draft_id"),
            session_id=startup.get("session_id"),
            next_required_input=startup.get("next_required_input"),
            teaching_mode=teaching_mode,
            metadata={
                "status": startup.get("status"),
            },
        )

    def _handle_worker_status(self) -> BillChatResponse:
        workers = self._get_workers()
        count = len(workers)
        if count == 0:
            return BillChatResponse(
                reply="No workers are currently online.",
                intent="worker_status",
                metadata={"worker_count": 0, "workers": []},
            )

        summaries = [
            {
                "uuid": uuid,
                "name": w.get("machine_name") or uuid,
                "status": w.get("status") or "unknown",
            }
            for uuid, w in workers.items()
        ]
        names_str = ", ".join(
            f"{s['name']} ({s['status']})" for s in summaries
        )
        reply = f"{count} worker{'s' if count != 1 else ''} online: {names_str}"
        return BillChatResponse(
            reply=reply,
            intent="worker_status",
            metadata={"worker_count": count, "workers": summaries},
        )

    def _handle_run_smart_sherpa(self, request: BillChatRequest) -> BillChatResponse:
        task_payload: dict[str, Any] = {
            "task_type": "smart_sherpa_sync",
            "workflow_id": "smart_sherpa_sync",
            "workflow_name": "smart_sherpa_sync",
            "tenant_id": request.tenant_id,
            "requested_by_user_id": request.user_id,
            "run_mode": "batch",
            "attach_to_existing": True,
            "require_existing_page": True,
            "allow_launch_fallback": False,
            "browser_profile_policy": "attach_existing_debug",
        }

        try:
            task_record = self._create_task(task_payload)
            task_id = _extract_task_id(task_record)
            return BillChatResponse(
                reply="Starting Smart Sherpa sync using the current clients page.",
                intent="run_smart_sherpa",
                action="task_queued",
                task_id=task_id,
                workflow_id="smart_sherpa_sync",
            )
        except Exception as exc:
            return BillChatResponse(
                reply=f"Could not start Smart Sherpa sync: {exc}",
                intent="run_smart_sherpa",
                metadata={"error": str(exc)},
            )

    def _handle_rename_worker(self, request: BillChatRequest) -> BillChatResponse:
        workers = self._get_workers()
        target_uuid, new_name = _parse_rename_command(request.message, workers)

        if not target_uuid:
            return BillChatResponse(
                reply="Which worker would you like to rename, and what should the new name be?",
                intent="rename_worker",
                next_required_input="worker_identifier_and_new_name",
            )
        if not new_name:
            return BillChatResponse(
                reply="What should the new name be for this worker?",
                intent="rename_worker",
                next_required_input="new_name",
                metadata={"target_uuid": target_uuid},
            )

        try:
            result = self._rename_worker(target_uuid, new_name)
            return BillChatResponse(
                reply=f"Renamed worker to {new_name}",
                intent="rename_worker",
                action="worker_renamed",
                metadata=result or {},
            )
        except Exception as exc:
            return BillChatResponse(
                reply=f"Could not rename worker: {exc}",
                intent="rename_worker",
                metadata={"error": str(exc)},
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_task_id(task_record: Any) -> str | None:
    """Extract task id from either a Pydantic model or a plain dict."""
    if task_record is None:
        return None
    task_id = getattr(task_record, "id", None)
    if task_id is None and isinstance(task_record, dict):
        task_id = task_record.get("id")
    return str(task_id) if task_id else None
