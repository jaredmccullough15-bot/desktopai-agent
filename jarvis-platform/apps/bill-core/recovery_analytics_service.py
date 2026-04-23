from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from playbook_service import get_all_playbooks, get_recent_executions
from recovery_analytics_schemas import ActionMetric, BucketMetric, PlaybookMetric, RecoveryAnalyticsSummary


MANUAL_ACTIONS = {
    "close_extra_tabs",
    "dismiss_product_review_modal",
    "return_to_client_list",
    "retry_last_client",
    "skip_last_client",
}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _bucketize(counter: Counter, limit: int = 10) -> list[BucketMetric]:
    return [BucketMetric(key=str(k), count=int(v)) for k, v in counter.most_common(limit)]


def _action_metrics(action_stats: dict[str, dict[str, int]]) -> list[ActionMetric]:
    metrics: list[ActionMetric] = []
    for action, values in action_stats.items():
        used = int(values.get("used", 0))
        success = int(values.get("success", 0))
        failed = int(values.get("failed", 0))
        rate = (success / used) if used else 0.0
        metrics.append(
            ActionMetric(
                action=action,
                used=used,
                success=success,
                failed=failed,
                success_rate=round(rate, 4),
            )
        )
    return metrics


def _incident_signature(task: dict[str, Any]) -> str:
    ctx = task.get("recovery_context") or {}
    signature = str(ctx.get("matched_problem_signature") or "").strip()
    if signature:
        return signature
    workflow = str((task.get("payload") or {}).get("workflow_name") or (task.get("payload") or {}).get("task_type") or "unknown")
    modal = "modal" if ctx.get("blocking_modal_detected") else "no_modal"
    tabs = "multi_tabs" if int(ctx.get("open_tabs_count") or 0) > 1 else "single_tab"
    error = str(ctx.get("last_error") or task.get("error") or "unknown_error").lower()
    token = "timeout" if "timeout" in error else "generic"
    return f"{workflow}|{modal}|{tabs}|{token}"


def _filter_tasks(tasks: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    workflow_name = str(filters.get("workflow_name") or "").strip().lower()
    machine_uuid = str(filters.get("machine_uuid") or "").strip().lower()
    recovery_status = str(filters.get("recovery_status") or "").strip().lower()
    start_dt = _parse_iso(filters.get("start_date"))
    end_dt = _parse_iso(filters.get("end_date"))

    def keep(task: dict[str, Any]) -> bool:
        payload = task.get("payload") or {}
        ctx = task.get("recovery_context") or {}
        task_workflow = str(ctx.get("workflow_name") or payload.get("workflow_name") or payload.get("task_type") or "").lower()
        task_machine = str(task.get("assigned_machine_uuid") or ctx.get("machine_uuid") or "").lower()
        status = str(task.get("status") or "").lower()
        updated = _parse_iso(task.get("updated_at") or ctx.get("paused_at"))

        if workflow_name and task_workflow != workflow_name:
            return False
        if machine_uuid and task_machine != machine_uuid:
            return False
        if recovery_status and status != recovery_status:
            return False
        if start_dt and updated and updated < start_dt:
            return False
        if end_dt and updated and updated > end_dt:
            return False
        return True

    return [t for t in tasks if keep(t)]


def build_recovery_analytics_summary(tasks: list[dict[str, Any]], filters: dict[str, Any] | None = None) -> RecoveryAnalyticsSummary:
    filters = filters or {}
    incidents = [
        t for t in tasks
        if t.get("recovery_context") or t.get("recovery_actions") or t.get("recovery_audit_trail")
    ]
    incidents = _filter_tasks(incidents, filters)

    summary = RecoveryAnalyticsSummary()
    summary.total_recovery_incidents = len(incidents)
    summary.currently_paused_recovery_tasks = len(
        [t for t in incidents if str(t.get("status") or "") in {"paused_for_human", "paused_for_auto_recovery"}]
    )

    by_workflow: Counter = Counter()
    by_machine: Counter = Counter()
    by_day: Counter = Counter()
    by_signature: Counter = Counter()
    by_error: Counter = Counter()

    action_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"used": 0, "success": 0, "failed": 0})
    pause_to_first_action: list[float] = []
    pause_to_resume: list[float] = []

    repeated_key_counter: Counter = Counter()

    for task in incidents:
        payload = task.get("payload") or {}
        ctx = task.get("recovery_context") or {}
        workflow = str(ctx.get("workflow_name") or payload.get("workflow_name") or payload.get("task_type") or "unknown")
        machine = str(task.get("assigned_machine_uuid") or ctx.get("machine_uuid") or "unknown")
        paused_at = _parse_iso(ctx.get("paused_at"))
        updated_at = _parse_iso(task.get("updated_at"))
        status = str(task.get("status") or "")

        by_workflow[workflow] += 1
        by_machine[machine] += 1
        if paused_at:
            by_day[paused_at.date().isoformat()] += 1

        signature = _incident_signature(task)
        by_signature[signature] += 1
        repeated_key_counter[f"{workflow}|{signature}"] += 1

        error_text = str(ctx.get("last_error") or task.get("error") or "").strip()
        if error_text:
            coarse = error_text.split(":", 1)[0][:120]
            by_error[coarse] += 1

        recovery_actions = task.get("recovery_actions") or []
        manual_actions = [
            a for a in recovery_actions
            if str(a.get("source") or "human") != "playbook_auto"
            and str(a.get("action") or "") in MANUAL_ACTIONS
        ]
        for action in manual_actions:
            name = str(action.get("action") or "")
            status_a = str(action.get("status") or "")
            action_stats[name]["used"] += 1
            if status_a == "completed":
                action_stats[name]["success"] += 1
            if status_a == "failed":
                action_stats[name]["failed"] += 1

        if paused_at and recovery_actions:
            first_requested = _parse_iso((recovery_actions[0] or {}).get("requested_at"))
            if first_requested:
                pause_to_first_action.append(max(0.0, (first_requested - paused_at).total_seconds()))

        if paused_at and updated_at and status in {"queued", "completed", "resolved_by_human"}:
            pause_to_resume.append(max(0.0, (updated_at - paused_at).total_seconds()))

    summary.incidents_by_workflow = _bucketize(by_workflow, limit=12)
    summary.incidents_by_machine_uuid = _bucketize(by_machine, limit=12)
    summary.incidents_by_day = sorted(_bucketize(by_day, limit=365), key=lambda x: x.key)
    summary.top_problem_signatures = _bucketize(by_signature, limit=10)
    summary.top_last_error_patterns = _bucketize(by_error, limit=10)

    all_action_metrics = _action_metrics(action_stats)
    summary.most_used_manual_actions = sorted(all_action_metrics, key=lambda m: m.used, reverse=True)[:10]
    summary.most_successful_manual_actions = sorted(
        [m for m in all_action_metrics if m.used >= 2],
        key=lambda m: (m.success_rate, m.used),
        reverse=True,
    )[:10]

    executions = get_recent_executions(limit=5000)
    auto_attempts = len(executions)
    auto_success = len([e for e in executions if bool(getattr(e, "success", False))])
    summary.auto_playbook_attempts = auto_attempts
    summary.auto_playbook_success_rate = round((auto_success / auto_attempts), 4) if auto_attempts else 0.0

    incidents_with_manual = 0
    incidents_manual_success = 0
    for task in incidents:
        manual_actions = [
            a for a in (task.get("recovery_actions") or [])
            if str(a.get("action") or "") in MANUAL_ACTIONS
        ]
        if manual_actions:
            incidents_with_manual += 1
            if any(str(a.get("status") or "") == "completed" for a in manual_actions):
                incidents_manual_success += 1
    summary.human_recovery_success_rate = (
        round((incidents_manual_success / incidents_with_manual), 4) if incidents_with_manual else 0.0
    )

    playbooks = get_all_playbooks(active_only=False)
    summary.candidate_playbooks_count = len([p for p in playbooks if str(getattr(p, "status", "")) == "candidate"])
    summary.trusted_playbooks_count = len([p for p in playbooks if str(getattr(p, "status", "")) == "trusted"])

    promoted = 0
    for task in incidents:
        for entry in (task.get("recovery_audit_trail") or []):
            if str(entry.get("event_type") or "") == "playbook_promoted_to_trusted":
                promoted += 1
    summary.playbooks_promoted_to_trusted = promoted

    if pause_to_first_action:
        summary.avg_pause_to_first_action_seconds = round(sum(pause_to_first_action) / len(pause_to_first_action), 2)
    if pause_to_resume:
        summary.avg_pause_to_resumed_seconds = round(sum(pause_to_resume) / len(pause_to_resume), 2)

    summary.repeated_incidents_same_workflow_signature = sum(1 for _, c in repeated_key_counter.items() if c > 1)

    return summary


def build_incident_analytics(tasks: list[dict[str, Any]], filters: dict[str, Any] | None = None) -> dict[str, Any]:
    filtered = _filter_tasks([
        t for t in tasks if t.get("recovery_context") or t.get("recovery_actions") or t.get("recovery_audit_trail")
    ], filters or {})

    by_workflow: Counter = Counter()
    by_signature: Counter = Counter()
    by_machine: Counter = Counter()
    by_day: Counter = Counter()

    multi_manual = 0
    auto_failed_then_human = 0
    incident_rows: list[dict[str, Any]] = []

    for t in filtered:
        ctx = t.get("recovery_context") or {}
        payload = t.get("payload") or {}
        workflow = str(ctx.get("workflow_name") or payload.get("workflow_name") or payload.get("task_type") or "unknown")
        machine = str(t.get("assigned_machine_uuid") or ctx.get("machine_uuid") or "unknown")
        signature = _incident_signature(t)
        paused_at = _parse_iso(ctx.get("paused_at"))
        day = paused_at.date().isoformat() if paused_at else "unknown"

        by_workflow[workflow] += 1
        by_signature[signature] += 1
        by_machine[machine] += 1
        by_day[day] += 1

        actions = t.get("recovery_actions") or []
        manual_actions = [a for a in actions if str(a.get("action") or "") in MANUAL_ACTIONS]
        if len(manual_actions) >= 2:
            multi_manual += 1
        auto_fail = any(
            str(a.get("source") or "") == "playbook_auto" and str(a.get("status") or "") == "failed"
            for a in actions
        )
        if auto_fail and manual_actions:
            auto_failed_then_human += 1

        incident_rows.append(
            {
                "task_id": t.get("id"),
                "workflow_name": workflow,
                "machine_uuid": machine,
                "status": t.get("status"),
                "problem_signature": signature,
                "paused_at": ctx.get("paused_at"),
                "updated_at": t.get("updated_at"),
                "manual_action_count": len(manual_actions),
                "auto_failed_before_human": auto_fail and bool(manual_actions),
                "last_error": ctx.get("last_error") or t.get("error"),
            }
        )

    return {
        "total": len(filtered),
        "incidents_by_workflow": [b.to_dict() for b in _bucketize(by_workflow, limit=100)],
        "incidents_by_signature": [b.to_dict() for b in _bucketize(by_signature, limit=100)],
        "incidents_by_machine": [b.to_dict() for b in _bucketize(by_machine, limit=100)],
        "incidents_over_time": [b.to_dict() for b in sorted(_bucketize(by_day, limit=365), key=lambda x: x.key)],
        "incidents_requiring_multiple_manual_actions": multi_manual,
        "incidents_auto_failed_before_human": auto_failed_then_human,
        "rows": sorted(incident_rows, key=lambda r: str(r.get("updated_at") or ""), reverse=True)[:200],
    }


def build_action_analytics(tasks: list[dict[str, Any]], filters: dict[str, Any] | None = None) -> dict[str, Any]:
    filtered = _filter_tasks([
        t for t in tasks if t.get("recovery_actions")
    ], filters or {})

    usage: dict[str, dict[str, int]] = defaultdict(lambda: {"used": 0, "success": 0, "failed": 0})
    sequence_success: dict[str, dict[str, int]] = defaultdict(lambda: {"used": 0, "success": 0, "failed": 0})
    after_failed_playbook: Counter = Counter()
    suggested_vs_chosen: dict[str, dict[str, int]] = defaultdict(lambda: {"recommended": 0, "chosen": 0})

    for t in filtered:
        actions = t.get("recovery_actions") or []
        had_failed_auto = any(
            str(a.get("source") or "") == "playbook_auto" and str(a.get("status") or "") == "failed"
            for a in actions
        )

        for a in actions:
            name = str(a.get("action") or "")
            status = str(a.get("status") or "")
            source = str(a.get("source") or "")

            if name in MANUAL_ACTIONS:
                usage[name]["used"] += 1
                if status == "completed":
                    usage[name]["success"] += 1
                if status == "failed":
                    usage[name]["failed"] += 1
                if had_failed_auto:
                    after_failed_playbook[name] += 1

            if name in {"playbook_auto_sequence", "suggested_action_sequence"}:
                seq = ",".join(str(x) for x in (a.get("action_sequence") or []))
                if seq:
                    sequence_success[seq]["used"] += 1
                    if status == "completed":
                        sequence_success[seq]["success"] += 1
                    if status == "failed":
                        sequence_success[seq]["failed"] += 1

            if source == "suggested_fix":
                if name == "suggested_action_sequence":
                    for step in (a.get("action_sequence") or []):
                        suggested_vs_chosen[str(step)]["chosen"] += 1
                elif name:
                    suggested_vs_chosen[name]["chosen"] += 1

        for entry in (t.get("recovery_audit_trail") or []):
            if str(entry.get("event_type") or "") != "suggestion_generated":
                continue
            detail = entry.get("details") or {}
            for step in (detail.get("recommended_action_sequence") or []):
                suggested_vs_chosen[str(step)]["recommended"] += 1

    usage_metrics = _action_metrics(usage)

    seq_rows = []
    for seq, vals in sequence_success.items():
        used = int(vals["used"])
        success = int(vals["success"])
        failed = int(vals["failed"])
        seq_rows.append(
            {
                "sequence": seq.split(",") if seq else [],
                "used": used,
                "success": success,
                "failed": failed,
                "success_rate": round((success / used), 4) if used else 0.0,
            }
        )

    return {
        "manual_action_usage": [m.to_dict() for m in sorted(usage_metrics, key=lambda x: x.used, reverse=True)],
        "manual_action_success": [m.to_dict() for m in sorted(usage_metrics, key=lambda x: x.success_rate, reverse=True)],
        "sequence_success_rates": sorted(seq_rows, key=lambda x: x["used"], reverse=True)[:50],
        "actions_after_failed_playbook": [b.to_dict() for b in _bucketize(after_failed_playbook, limit=20)],
        "suggested_vs_chosen": [
            {"action": action, **vals}
            for action, vals in sorted(suggested_vs_chosen.items(), key=lambda i: i[0])
        ],
    }


def build_playbook_analytics(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    filters = filters or {}
    workflow_name = str(filters.get("workflow_name") or "").strip().lower()
    playbook_status = str(filters.get("playbook_status") or "").strip().lower()

    playbooks = get_all_playbooks(active_only=False)
    executions = get_recent_executions(limit=5000)

    rows: list[PlaybookMetric] = []
    promotions_over_time: Counter = Counter()

    for pb in playbooks:
        pb_dict = pb.to_dict() if hasattr(pb, "to_dict") else pb
        wf = str(pb_dict.get("workflow_name") or "unknown")
        status = str(pb_dict.get("status") or "")
        if workflow_name and wf.lower() != workflow_name:
            continue
        if playbook_status and status.lower() != playbook_status:
            continue

        attempted = int(pb_dict.get("attempted_count") or 0)
        success = int(pb_dict.get("success_count") or 0)
        failed = int(pb_dict.get("failure_count") or 0)
        rows.append(
            PlaybookMetric(
                playbook_id=str(pb_dict.get("playbook_id") or ""),
                workflow_name=wf,
                status=status,
                attempted_count=attempted,
                success_count=success,
                failure_count=failed,
                success_rate=round((success / attempted), 4) if attempted else 0.0,
                confidence_score=float(pb_dict.get("confidence_score") or 0.0),
                last_used_at=pb_dict.get("last_used_at") or None,
            )
        )

        updated = _parse_iso(pb_dict.get("updated_at"))
        if status == "trusted" and updated:
            promotions_over_time[updated.date().isoformat()] += 1

    exec_by_playbook: dict[str, dict[str, int]] = defaultdict(lambda: {"used": 0, "success": 0, "failed": 0})
    for ex in executions:
        pb_id = str(getattr(ex, "playbook_id", "") or "")
        if not pb_id:
            continue
        exec_by_playbook[pb_id]["used"] += 1
        if bool(getattr(ex, "success", False)):
            exec_by_playbook[pb_id]["success"] += 1
        else:
            exec_by_playbook[pb_id]["failed"] += 1

    row_dicts = [r.to_dict() for r in rows]

    top_trusted = [r for r in row_dicts if r.get("status") == "trusted"]
    top_trusted.sort(key=lambda r: (r.get("success_rate", 0), r.get("attempted_count", 0)), reverse=True)

    highest_failure = list(row_dicts)
    highest_failure.sort(key=lambda r: (r.get("failure_count", 0), r.get("attempted_count", 0)), reverse=True)

    nearing_trust = [
        r for r in row_dicts
        if r.get("status") == "candidate"
        and int(r.get("success_count") or 0) >= 1
        and float(r.get("confidence_score") or 0.0) >= 0.55
    ]
    nearing_trust.sort(key=lambda r: (r.get("success_count", 0), r.get("confidence_score", 0)), reverse=True)

    return {
        "total_playbooks": len(row_dicts),
        "top_performing_trusted_playbooks": top_trusted[:20],
        "highest_failure_playbooks": highest_failure[:20],
        "candidate_playbooks_nearing_trust": nearing_trust[:20],
        "promotions_over_time": [b.to_dict() for b in sorted(_bucketize(promotions_over_time, 365), key=lambda x: x.key)],
        "auto_apply_usage_counts": [
            {"playbook_id": pid, **vals}
            for pid, vals in sorted(exec_by_playbook.items(), key=lambda i: i[1]["used"], reverse=True)
        ],
        "rows": row_dicts,
    }


def build_recovery_timeline(tasks: list[dict[str, Any]], filters: dict[str, Any] | None = None) -> dict[str, Any]:
    filtered = _filter_tasks([
        t for t in tasks if t.get("recovery_audit_trail")
    ], filters or {})

    events: list[dict[str, Any]] = []
    for task in filtered:
        workflow = str((task.get("recovery_context") or {}).get("workflow_name") or (task.get("payload") or {}).get("workflow_name") or "unknown")
        for entry in (task.get("recovery_audit_trail") or []):
            events.append(
                {
                    "task_id": task.get("id"),
                    "workflow_name": workflow,
                    "machine_uuid": task.get("assigned_machine_uuid") or (task.get("recovery_context") or {}).get("machine_uuid"),
                    "event_type": entry.get("event_type"),
                    "timestamp": entry.get("timestamp"),
                    "details": entry.get("details") or {},
                }
            )

    events.sort(key=lambda e: str(e.get("timestamp") or ""), reverse=True)

    failed_self_healing = [
        e for e in events
        if str(e.get("event_type") or "") in {"playbook_auto_apply_failed", "suggestion_failed"}
    ]

    return {
        "total_events": len(events),
        "recent_events": events[:300],
        "recent_failed_self_healing_attempts": failed_self_healing[:100],
    }
