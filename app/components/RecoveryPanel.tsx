"use client";

import { useEffect, useRef, useState, useCallback } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

export type PausedTask = {
  id: string;
  status: string;
  workflow_name?: string | null;
  assigned_machine_uuid?: string | null;
  error?: string | null;
  updated_at?: string | null;
  recovery_context?: RecoveryContext | null;
  is_auto_recovery?: boolean;
};

export type RecoveryContext = {
  // identity
  task_id?: string;
  workflow_name?: string | null;
  assigned_machine_uuid?: string | null;
  // issue signals
  last_error?: string | null;
  open_tabs_count?: number | null;
  blocking_modal_detected?: boolean | null;
  modal_type?: string | null;
  current_url?: string | null;
  current_page_number?: number | null;
  // client progress
  last_client_attempted?: string | null;
  last_successful_client?: string | null;
  // phase 6.5 playbook fields
  matched_playbook_id?: string | null;
  matched_problem_signature?: string | null;
  playbook_auto_attempted?: boolean | null;
  playbook_auto_attempt_result?: string | null;
  candidate_playbook_created?: boolean | null;
  learned_from_human_recovery?: boolean | null;
  is_auto_recovery?: boolean | null;
  // control
  recovery_attempt_count?: number | null;
  can_submit_new_action?: boolean | null;
  // sub-objects
  actions?: RecoveryAction[];
  audit_trail?: RecoveryAuditEntry[];
};

export type RecoveryAction = {
  action_id?: string;
  action?: string;
  status?: string; // "pending" | "in_progress" | "completed" | "failed"
  timestamp?: string | null;
  result_message?: string | null;
  error_details?: string | null;
  operator_notes?: string | null;
  is_playbook_auto_action?: boolean | null;
};

export type RecoveryAuditEntry = {
  id?: string;
  event?: string;
  timestamp?: string | null;
  details?: Record<string, unknown> | null;
};

type ActionFeedback = {
  action: string;
  success: boolean;
  message: string;
};

type RecoverySuggestionWarning = {
  code?: string;
  message?: string;
  severity?: string;
};

type RecoverySuggestionBasis = {
  matched_playbook_id?: string | null;
  matched_problem_signature?: string | null;
  modal_detected?: boolean;
  tab_count?: number;
  last_error_contains?: string[];
  recent_action_failures?: string[];
  workflow_match?: boolean;
  auto_playbook_failed?: boolean;
  current_page_type?: string | null;
  url_hint?: string | null;
};

type RecoverySuggestion = {
  suggestion_id?: string;
  task_id?: string;
  workflow_name?: string;
  recommended_action_sequence?: string[];
  primary_action?: string;
  confidence?: number;
  reasoning_summary?: string;
  based_on?: RecoverySuggestionBasis;
  warnings?: RecoverySuggestionWarning[];
  generated_at?: string;
  source?: "rule_based" | "playbook_based" | "ai_assisted" | string;
};

type RecoveryContextApiResponse = {
  task_id?: string;
  status?: string;
  recovery_context?: Record<string, unknown>;
  recovery_actions?: Array<Record<string, unknown>>;
  recovery_attempt_count?: number;
  can_submit_new_action?: boolean;
  is_auto_recovery?: boolean;
  last_error?: string;
  matched_playbook_id?: string | null;
  matched_problem_signature?: string | null;
  playbook_auto_attempted?: boolean;
  playbook_auto_attempt_result?: string | null;
  candidate_playbook_created?: boolean;
  learned_from_human_recovery?: boolean;
  audit_trail?: Array<Record<string, unknown>>;
};

// ── Constants ─────────────────────────────────────────────────────────────────

const QUEUE_POLL_MS = 8_000;
const DETAIL_POLL_MS = 5_000;

const BUTTON_SECONDARY =
  "rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-200 transition-colors hover:border-slate-600 hover:bg-slate-800 active:scale-[.97] disabled:pointer-events-none disabled:opacity-40";

const BUTTON_DANGER =
  "rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-300 transition-colors hover:bg-rose-500/20 active:scale-[.97] disabled:pointer-events-none disabled:opacity-40";

const BUTTON_ACCENT_GHOST =
  "rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-300 transition-colors hover:bg-cyan-500/20 active:scale-[.97] disabled:pointer-events-none disabled:opacity-40";

const ACTION_DEFS: { action: string; label: string; description: string; variant: "secondary" | "danger" | "accent" }[] = [
  {
    action: "close_extra_tabs",
    label: "Close Extra Tabs",
    description: "Close all browser tabs except the main one",
    variant: "secondary",
  },
  {
    action: "dismiss_product_review_modal",
    label: "Dismiss Modal",
    description: "Dismiss a blocking product review or pop-up modal",
    variant: "secondary",
  },
  {
    action: "return_to_client_list",
    label: "Return to Client List",
    description: "Navigate back to the client list page",
    variant: "accent",
  },
  {
    action: "retry_last_client",
    label: "Retry Last Client",
    description: "Retry the last client that was attempted",
    variant: "accent",
  },
  {
    action: "skip_last_client",
    label: "Skip Last Client",
    description: "Mark last client as skipped and continue",
    variant: "danger",
  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  return `${Math.floor(diff / 3_600_000)}h ago`;
}

function shortId(id: string): string {
  return id.length > 8 ? `…${id.slice(-8)}` : id;
}

function statusBadge(status: string): string {
  if (status === "paused_for_human")
    return "rounded px-1.5 py-0.5 text-[10px] font-semibold bg-violet-500/20 text-violet-300 border border-violet-500/30";
  if (status === "paused_for_auto_recovery")
    return "rounded px-1.5 py-0.5 text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30";
  if (status === "running")
    return "rounded px-1.5 py-0.5 text-[10px] font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30";
  if (status === "completed")
    return "rounded px-1.5 py-0.5 text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
  if (status === "failed")
    return "rounded px-1.5 py-0.5 text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30";
  return "rounded px-1.5 py-0.5 text-[10px] font-semibold bg-slate-700/60 text-slate-400 border border-slate-600/30";
}

function actionStatusBadge(status: string | undefined): string {
  if (status === "completed")
    return "rounded px-1.5 py-0.5 text-[10px] font-semibold bg-emerald-500/20 text-emerald-300";
  if (status === "failed")
    return "rounded px-1.5 py-0.5 text-[10px] font-semibold bg-rose-500/20 text-rose-300";
  if (status === "in_progress")
    return "rounded px-1.5 py-0.5 text-[10px] font-semibold bg-amber-500/20 text-amber-300";
  return "rounded px-1.5 py-0.5 text-[10px] font-semibold bg-slate-700/60 text-slate-400";
}

// ── Component ─────────────────────────────────────────────────────────────────

interface RecoveryPanelProps {
  apiBase: string;
}

export default function RecoveryPanel({ apiBase }: RecoveryPanelProps) {
  const [pausedTasks, setPausedTasks] = useState<PausedTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [recoveryContext, setRecoveryContext] = useState<RecoveryContext | null>(null);
  const [loadingQueue, setLoadingQueue] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [submittingAction, setSubmittingAction] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<ActionFeedback | null>(null);
  const [operatorNotes, setOperatorNotes] = useState("");
  const [showRawJson, setShowRawJson] = useState(false);
  const [showAuditTrail, setShowAuditTrail] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [suggestion, setSuggestion] = useState<RecoverySuggestion | null>(null);
  const [loadingSuggestion, setLoadingSuggestion] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [applyingSuggestion, setApplyingSuggestion] = useState(false);

  const queueTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const detailTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Fetchers ───────────────────────────────────────────────────────────────

  const loadQueue = useCallback(async () => {
    setLoadingQueue(true);
    setQueueError(null);
    try {
      const res = await fetch(
        `${apiBase}/api/tasks/paused-for-human-recovery?include_auto=true`,
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as { tasks?: PausedTask[] };
      setPausedTasks(data.tasks ?? []);
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : "Failed to load recovery queue");
    } finally {
      setLoadingQueue(false);
    }
  }, [apiBase]);

  const loadDetail = useCallback(async (taskId: string) => {
    setLoadingDetail(true);
    try {
      const res = await fetch(`${apiBase}/api/tasks/${taskId}/recovery-context`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as RecoveryContextApiResponse;
      const context = (data.recovery_context ?? {}) as Record<string, unknown>;
      const actionsRaw = (data.recovery_actions ?? []) as Array<Record<string, unknown>>;
      const auditRaw = (data.audit_trail ?? []) as Array<Record<string, unknown>>;

      const normalized: RecoveryContext = {
        task_id: data.task_id,
        workflow_name: String(context.workflow_name ?? "") || null,
        assigned_machine_uuid: String((context.machine_uuid ?? "") || "") || null,
        last_error: String((data.last_error ?? context.last_error ?? "") || "") || null,
        open_tabs_count: context.open_tabs_count != null ? Number(context.open_tabs_count) : null,
        blocking_modal_detected: context.blocking_modal_detected != null ? Boolean(context.blocking_modal_detected) : null,
        modal_type: String((context.modal_type ?? "") || "") || null,
        current_url: String((context.current_url ?? "") || "") || null,
        current_page_number: context.current_page_number != null ? Number(context.current_page_number) : null,
        last_client_attempted: String((context.last_client_attempted ?? "") || "") || null,
        last_successful_client: String((context.last_successful_client ?? "") || "") || null,
        matched_playbook_id: data.matched_playbook_id ?? null,
        matched_problem_signature: data.matched_problem_signature ?? null,
        playbook_auto_attempted: Boolean(data.playbook_auto_attempted),
        playbook_auto_attempt_result: data.playbook_auto_attempt_result ?? null,
        candidate_playbook_created: Boolean(data.candidate_playbook_created),
        learned_from_human_recovery: Boolean(data.learned_from_human_recovery),
        is_auto_recovery: Boolean(data.is_auto_recovery),
        recovery_attempt_count: data.recovery_attempt_count ?? null,
        can_submit_new_action: data.can_submit_new_action ?? null,
        actions: actionsRaw.map((item) => ({
          action_id: String(item.action_id ?? "") || undefined,
          action: String(item.action ?? "") || undefined,
          status: String(item.status ?? "") || undefined,
          timestamp: (String(item.completed_at ?? item.requested_at ?? "") || undefined),
          result_message: String(item.result_message ?? "") || undefined,
          error_details: String(item.error_details ?? "") || undefined,
          operator_notes: String(item.operator_notes ?? "") || undefined,
          is_playbook_auto_action: String(item.source ?? "") === "playbook_auto",
        })),
        audit_trail: auditRaw.map((entry) => ({
          id: String(entry.entry_id ?? "") || undefined,
          event: String(entry.event_type ?? "") || undefined,
          timestamp: String(entry.timestamp ?? "") || undefined,
          details: (entry.details as Record<string, unknown> | undefined) ?? null,
        })),
      };
      setRecoveryContext(normalized);
    } catch {
      // detail fetch failure is non-blocking
    } finally {
      setLoadingDetail(false);
    }
  }, [apiBase]);

  const loadSuggestion = useCallback(async (taskId: string, refresh = false) => {
    setLoadingSuggestion(true);
    setSuggestionError(null);
    try {
      const suffix = refresh ? "?refresh=true" : "";
      const res = await fetch(`${apiBase}/api/tasks/${taskId}/recovery-suggestion${suffix}`, { cache: "no-store" });
      if (!res.ok) {
        const errData = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errData.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as { suggestion?: RecoverySuggestion };
      setSuggestion(data.suggestion ?? null);
    } catch (err) {
      setSuggestion(null);
      setSuggestionError(err instanceof Error ? err.message : "Failed to load suggestion");
    } finally {
      setLoadingSuggestion(false);
    }
  }, [apiBase]);

  // ── Polling setup ──────────────────────────────────────────────────────────

  useEffect(() => {
    void loadQueue();
    queueTimerRef.current = setInterval(() => void loadQueue(), QUEUE_POLL_MS);
    return () => {
      if (queueTimerRef.current) clearInterval(queueTimerRef.current);
    };
  }, [loadQueue]);

  useEffect(() => {
    if (!selectedTaskId) return;
    void loadDetail(selectedTaskId);
    detailTimerRef.current = setInterval(() => void loadDetail(selectedTaskId), DETAIL_POLL_MS);
    return () => {
      if (detailTimerRef.current) clearInterval(detailTimerRef.current);
    };
  }, [selectedTaskId, loadDetail]);

  useEffect(() => {
    if (!selectedTaskId) return;
    void loadSuggestion(selectedTaskId, false);
  }, [selectedTaskId, loadSuggestion]);

  // ── Actions ────────────────────────────────────────────────────────────────

  const handleSelectTask = (task: PausedTask) => {
    if (task.id === selectedTaskId) return;
    setSelectedTaskId(task.id);
    setRecoveryContext(null);
    setActionFeedback(null);
    setOperatorNotes("");
    setShowRawJson(false);
    setShowAuditTrail(false);
    setSuggestion(null);
    setSuggestionError(null);
  };

  const handleSubmitAction = async (action: string) => {
    if (!selectedTaskId) return;
    setSubmittingAction(action);
    setActionFeedback(null);
    try {
      const res = await fetch(`${apiBase}/api/tasks/${selectedTaskId}/recovery-action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, operator_notes: operatorNotes || null }),
      });
      if (!res.ok) {
        const errData = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errData.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as { message?: string };
      setActionFeedback({
        action,
        success: true,
        message: data.message ?? "Action submitted successfully",
      });
      setOperatorNotes("");
      // Refresh detail immediately
      await loadDetail(selectedTaskId);
      // Refresh queue
      await loadQueue();
    } catch (err) {
      setActionFeedback({
        action,
        success: false,
        message: err instanceof Error ? err.message : "Action failed",
      });
    } finally {
      setSubmittingAction(null);
    }
  };

  const handleApplySuggestedFix = async () => {
    if (!selectedTaskId) return;
    setApplyingSuggestion(true);
    setActionFeedback(null);
    try {
      const res = await fetch(`${apiBase}/api/tasks/${selectedTaskId}/apply-suggested-fix`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operator_notes: operatorNotes || null }),
      });
      if (!res.ok) {
        const errData = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errData.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as { message?: string; sequence_mode?: boolean };
      setActionFeedback({
        action: "suggested_fix",
        success: true,
        message: data.sequence_mode
          ? (data.message ?? "Suggested sequence queued")
          : "Suggested first action queued",
      });
      await loadDetail(selectedTaskId);
      await loadQueue();
      await loadSuggestion(selectedTaskId, true);
    } catch (err) {
      setActionFeedback({
        action: "suggested_fix",
        success: false,
        message: err instanceof Error ? err.message : "Failed to apply suggested fix",
      });
    } finally {
      setApplyingSuggestion(false);
    }
  };

  // ── Derived state ──────────────────────────────────────────────────────────

  const selectedTask = pausedTasks.find((t) => t.id === selectedTaskId) ?? null;
  const taskStillPaused =
    selectedTaskId !== null &&
    (selectedTask !== null ||
      (recoveryContext !== null &&
        (recoveryContext.task_id === selectedTaskId)));
  const canSubmit = !submittingAction && (recoveryContext?.can_submit_new_action !== false);

  // ── Render ─────────────────────────────────────────────────────────────────

  const totalPaused = pausedTasks.length;
  const autoPaused = pausedTasks.filter((t) => t.status === "paused_for_auto_recovery").length;

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 shadow-lg shadow-black/25">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-semibold text-slate-100">Recovery Queue</h2>
          <div className="flex items-center gap-1.5">
            {totalPaused > 0 && (
              <span className="rounded-full bg-violet-500/20 px-2 py-0.5 text-xs font-semibold text-violet-300">
                {totalPaused}
              </span>
            )}
            {autoPaused > 0 && (
              <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-semibold text-amber-300 border border-amber-500/20">
                {autoPaused} auto
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => void loadQueue()}
          disabled={loadingQueue}
          className={BUTTON_ACCENT_GHOST}
        >
          {loadingQueue ? "Refreshing…" : "↻ Refresh"}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* ── Left: Queue ───────────────────────────────────────────────── */}
        <div className="flex flex-col gap-2">
          {queueError && (
            <div className="rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
              {queueError}
            </div>
          )}

          {!loadingQueue && pausedTasks.length === 0 && (
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-8 text-center">
              <p className="text-sm text-slate-500">No tasks paused for recovery</p>
              <p className="mt-1 text-xs text-slate-600">Workers are running normally</p>
            </div>
          )}

          {pausedTasks.map((task) => (
            <button
              key={task.id}
              onClick={() => handleSelectTask(task)}
              className={`w-full rounded-xl border px-4 py-3 text-left transition-colors ${
                selectedTaskId === task.id
                  ? "border-violet-500/40 bg-violet-500/10"
                  : "border-slate-800 bg-slate-900/60 hover:border-slate-700 hover:bg-slate-800/60"
              }`}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="font-mono text-xs text-slate-400">{shortId(task.id)}</span>
                <div className="flex items-center gap-1">
                  {task.is_auto_recovery && (
                    <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-amber-400">
                      auto
                    </span>
                  )}
                  <span className={statusBadge(task.status ?? "")}>{task.status?.replace(/_/g, " ")}</span>
                </div>
              </div>
              <p className="mb-1 text-sm font-medium text-slate-200 leading-tight">
                {task.workflow_name ?? "Unknown workflow"}
              </p>
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">
                  {task.assigned_machine_uuid
                    ? `Worker: …${task.assigned_machine_uuid.slice(-6)}`
                    : "No worker"}
                </span>
                <span className="text-xs text-slate-600">{timeAgo(task.updated_at)}</span>
              </div>
              {task.error && (
                <p className="mt-1 truncate text-xs text-rose-400/80">{task.error}</p>
              )}
            </button>
          ))}
        </div>

        {/* ── Right: Detail Panel ───────────────────────────────────────── */}
        <div className="flex flex-col gap-3">
          {!selectedTaskId && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-10 text-center">
              <p className="text-sm text-slate-500">Select a task to view details</p>
            </div>
          )}

          {selectedTaskId && !taskStillPaused && !loadingDetail && (
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-4">
              <p className="text-sm font-medium text-emerald-300">Task no longer paused</p>
              <p className="mt-0.5 text-xs text-emerald-400/70">
                Task was resumed or completed. Select another task.
              </p>
            </div>
          )}

          {selectedTaskId && (recoveryContext || loadingDetail) && (
            <>
              {/* Task header */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-slate-400">{shortId(selectedTaskId)}</span>
                  {selectedTask && (
                    <span className={statusBadge(selectedTask.status ?? "")}>
                      {selectedTask.status?.replace(/_/g, " ")}
                    </span>
                  )}
                </div>
                <p className="text-sm font-semibold text-slate-100">
                  {recoveryContext?.workflow_name ?? selectedTask?.workflow_name ?? "Unknown workflow"}
                </p>
                {recoveryContext?.assigned_machine_uuid && (
                  <p className="mt-0.5 text-xs text-slate-500">
                    Worker: …{recoveryContext.assigned_machine_uuid.slice(-8)}
                  </p>
                )}
              </div>

              {/* Issue summary */}
              <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-cyan-500">Suggested Fix</p>
                  <div className="flex items-center gap-2">
                    {suggestion?.source && (
                      <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-0.5 text-[9px] font-semibold text-cyan-300">
                        {suggestion.source}
                      </span>
                    )}
                    {typeof suggestion?.confidence === "number" && (
                      <span className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[9px] font-semibold text-slate-300">
                        {Math.round((suggestion.confidence ?? 0) * 100)}%
                      </span>
                    )}
                  </div>
                </div>

                {loadingSuggestion && (
                  <p className="text-xs text-slate-500">Generating suggestion...</p>
                )}

                {!loadingSuggestion && suggestionError && (
                  <p className="text-xs text-rose-300">Suggestion unavailable: {suggestionError}</p>
                )}

                {!loadingSuggestion && !suggestionError && suggestion && (
                  <div className="space-y-2">
                    <p className="text-xs text-slate-200">
                      Primary recommendation: <span className="font-semibold text-cyan-300">{(suggestion.primary_action ?? "").replace(/_/g, " ")}</span>
                    </p>
                    <p className="text-[11px] text-slate-400 leading-relaxed">{suggestion.reasoning_summary}</p>

                    {(suggestion.recommended_action_sequence ?? []).length > 0 && (
                      <div className="rounded-lg border border-slate-800 bg-slate-950 px-2 py-1.5">
                        <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">Sequence</p>
                        <div className="flex flex-wrap gap-1">
                          {(suggestion.recommended_action_sequence ?? []).map((step, idx) => (
                            <span key={`${step}-${idx}`} className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                              {idx + 1}. {step.replace(/_/g, " ")}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {suggestion.based_on && (
                      <div className="text-[10px] text-slate-500">
                        {(suggestion.based_on.matched_problem_signature || suggestion.based_on.modal_detected || suggestion.based_on.tab_count != null) && (
                          <p>
                            Basis: {suggestion.based_on.matched_problem_signature ?? "-"}
                            {suggestion.based_on.modal_detected ? " · modal" : ""}
                            {suggestion.based_on.tab_count != null ? ` · tabs=${suggestion.based_on.tab_count}` : ""}
                          </p>
                        )}
                      </div>
                    )}

                    {(suggestion.warnings ?? []).length > 0 && (
                      <div className="space-y-1">
                        {(suggestion.warnings ?? []).map((warn, idx) => (
                          <p key={`warn-${idx}`} className="text-[11px] text-amber-300">
                            - {warn.message}
                          </p>
                        ))}
                      </div>
                    )}

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => void handleApplySuggestedFix()}
                        disabled={!canSubmit || applyingSuggestion || loadingSuggestion || !suggestion}
                        className={BUTTON_ACCENT_GHOST}
                      >
                        {applyingSuggestion ? "Applying..." : "Apply Suggested Fix"}
                      </button>
                      <button
                        onClick={() => selectedTaskId && void loadSuggestion(selectedTaskId, true)}
                        disabled={loadingSuggestion || !selectedTaskId}
                        className={BUTTON_SECONDARY}
                      >
                        Refresh Suggestion
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Issue summary */}
              {recoveryContext?.last_error && (
                <div className="rounded-xl border border-rose-500/20 bg-rose-500/8 px-4 py-3">
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-rose-400">
                    Last Error
                  </p>
                  <p className="text-xs leading-relaxed text-rose-300">{recoveryContext.last_error}</p>
                </div>
              )}

              {/* Checkpoint signals */}
              {(recoveryContext?.open_tabs_count != null ||
                recoveryContext?.blocking_modal_detected != null ||
                recoveryContext?.current_page_number != null ||
                recoveryContext?.last_client_attempted) && (
                <div className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    Checkpoint State
                  </p>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                    {recoveryContext?.open_tabs_count != null && (
                      <>
                        <span className="text-xs text-slate-500">Open tabs</span>
                        <span className={`text-xs font-mono ${recoveryContext.open_tabs_count > 1 ? "text-amber-300" : "text-slate-300"}`}>
                          {recoveryContext.open_tabs_count}
                        </span>
                      </>
                    )}
                    {recoveryContext?.blocking_modal_detected != null && (
                      <>
                        <span className="text-xs text-slate-500">Modal detected</span>
                        <span className={`text-xs font-mono ${recoveryContext.blocking_modal_detected ? "text-rose-300" : "text-slate-500"}`}>
                          {recoveryContext.blocking_modal_detected
                            ? `Yes${recoveryContext.modal_type ? ` (${recoveryContext.modal_type})` : ""}`
                            : "No"}
                        </span>
                      </>
                    )}
                    {recoveryContext?.current_page_number != null && (
                      <>
                        <span className="text-xs text-slate-500">Page #</span>
                        <span className="text-xs font-mono text-slate-300">
                          {recoveryContext.current_page_number}
                        </span>
                      </>
                    )}
                    {recoveryContext?.last_client_attempted && (
                      <>
                        <span className="text-xs text-slate-500">Last client</span>
                        <span className="text-xs font-mono text-slate-300 truncate">
                          {recoveryContext.last_client_attempted}
                        </span>
                      </>
                    )}
                    {recoveryContext?.last_successful_client && (
                      <>
                        <span className="text-xs text-slate-500">Last success</span>
                        <span className="text-xs font-mono text-emerald-300 truncate">
                          {recoveryContext.last_successful_client}
                        </span>
                      </>
                    )}
                    {recoveryContext?.current_url && (
                      <>
                        <span className="text-xs text-slate-500">Current URL</span>
                        <span className="col-span-1 truncate text-xs font-mono text-slate-400" title={recoveryContext.current_url}>
                          {recoveryContext.current_url.replace(/^https?:\/\//, "").slice(0, 40)}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              )}

              {/* Playbook / learned-fix info */}
              {(recoveryContext?.matched_playbook_id ||
                recoveryContext?.playbook_auto_attempted ||
                recoveryContext?.candidate_playbook_created ||
                recoveryContext?.learned_from_human_recovery) && (
                <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-cyan-500">
                    Learned Fix
                  </p>
                  <div className="flex flex-col gap-1.5">
                    {recoveryContext?.matched_problem_signature && (
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs text-slate-500">Signature</span>
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-cyan-300">
                          {recoveryContext.matched_problem_signature}
                        </span>
                      </div>
                    )}
                    {recoveryContext?.playbook_auto_attempted && (
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs text-slate-500">Auto-attempted</span>
                        <span className={`text-xs font-medium ${recoveryContext.playbook_auto_attempt_result === "success" ? "text-emerald-300" : "text-rose-300"}`}>
                          {recoveryContext.playbook_auto_attempt_result ?? "attempted"}
                        </span>
                      </div>
                    )}
                    {recoveryContext?.candidate_playbook_created && (
                      <div className="flex items-center gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
                        <span className="text-xs text-cyan-300">Candidate playbook created from this fix</span>
                      </div>
                    )}
                    {recoveryContext?.learned_from_human_recovery && (
                      <div className="flex items-center gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                        <span className="text-xs text-emerald-300">This fix was learned from human recovery</span>
                      </div>
                    )}
                    {recoveryContext?.matched_playbook_id && (
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs text-slate-500">Playbook ID</span>
                        <span className="font-mono text-[10px] text-slate-400">
                          …{recoveryContext.matched_playbook_id.slice(-8)}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Operator notes input */}
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  Operator Notes (optional)
                </label>
                <textarea
                  value={operatorNotes}
                  onChange={(e) => setOperatorNotes(e.target.value)}
                  placeholder="Describe what you observed or why you chose this action…"
                  rows={2}
                  disabled={!canSubmit}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 placeholder-slate-600 resize-none focus:border-cyan-500/50 focus:outline-none disabled:opacity-40"
                />
              </div>

              {/* Action feedback */}
              {actionFeedback && (
                <div
                  className={`rounded-lg border px-3 py-2 text-xs ${
                    actionFeedback.success
                      ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                      : "border-rose-500/20 bg-rose-500/10 text-rose-300"
                  }`}
                >
                  {actionFeedback.message}
                </div>
              )}

              {/* Action buttons */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
                <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  Recovery Actions
                  {recoveryContext?.recovery_attempt_count != null &&
                    recoveryContext.recovery_attempt_count > 0 && (
                      <span className="ml-2 text-slate-600">
                        ({recoveryContext.recovery_attempt_count} attempt
                        {recoveryContext.recovery_attempt_count !== 1 ? "s" : ""})
                      </span>
                    )}
                </p>
                <div className="flex flex-col gap-1.5">
                  {ACTION_DEFS.map(({ action, label, description, variant }) => {
                    const isSubmitting = submittingAction === action;
                    const buttonClass =
                      variant === "danger"
                        ? BUTTON_DANGER
                        : variant === "accent"
                        ? BUTTON_ACCENT_GHOST
                        : BUTTON_SECONDARY;
                    return (
                      <button
                        key={action}
                        onClick={() => void handleSubmitAction(action)}
                        disabled={!canSubmit || !!submittingAction}
                        title={description}
                        className={`${buttonClass} flex w-full items-center justify-between`}
                      >
                        <span>{label}</span>
                        {isSubmitting && (
                          <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Action history */}
              {recoveryContext?.actions && recoveryContext.actions.length > 0 && (
                <div className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    Action History ({recoveryContext.actions.length})
                  </p>
                  <div className="flex flex-col gap-2">
                    {[...recoveryContext.actions].reverse().map((a, idx) => (
                      <div key={a.action_id ?? idx} className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="text-xs font-mono text-slate-300">
                              {a.action?.replace(/_/g, " ")}
                            </span>
                            {a.is_playbook_auto_action && (
                              <span className="rounded bg-amber-500/20 px-1 py-0.5 text-[9px] font-bold text-amber-400">
                                auto
                              </span>
                            )}
                            <span className={actionStatusBadge(a.status)}>{a.status}</span>
                          </div>
                          {a.result_message && (
                            <p className="mt-0.5 text-[10px] text-slate-500 leading-snug">
                              {a.result_message.length > 120
                                ? a.result_message.slice(0, 120) + "…"
                                : a.result_message}
                            </p>
                          )}
                        </div>
                        <span className="shrink-0 text-[10px] text-slate-600">
                          {timeAgo(a.timestamp)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Audit trail toggle */}
              {recoveryContext?.audit_trail && recoveryContext.audit_trail.length > 0 && (
                <div className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
                  <button
                    onClick={() => setShowAuditTrail((v) => !v)}
                    className="flex w-full items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-slate-500"
                  >
                    <span>Audit Trail ({recoveryContext.audit_trail.length})</span>
                    <span>{showAuditTrail ? "▲" : "▼"}</span>
                  </button>
                  {showAuditTrail && (
                    <div className="mt-2 flex flex-col gap-1.5 border-l-2 border-slate-700 pl-3">
                      {[...recoveryContext.audit_trail].reverse().map((entry, idx) => (
                        <div key={entry.id ?? idx}>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-mono text-slate-300">
                              {entry.event?.replace(/_/g, " ")}
                            </span>
                            <span className="shrink-0 text-[10px] text-slate-600">
                              {timeAgo(entry.timestamp)}
                            </span>
                          </div>
                          {entry.details && Object.keys(entry.details).length > 0 && (
                            <p className="text-[10px] text-slate-500">
                              {Object.entries(entry.details)
                                .slice(0, 3)
                                .map(([k, v]) => `${k}: ${String(v)}`)
                                .join(" · ")}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Raw JSON toggle */}
              <div>
                <button
                  onClick={() => setShowRawJson((v) => !v)}
                  className={BUTTON_SECONDARY + " w-full justify-center text-xs"}
                >
                  {showRawJson ? "Hide Raw Context" : "Show Raw Context"}
                </button>
                {showRawJson && (
                  <pre className="mt-2 max-h-64 overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-3 text-[10px] leading-relaxed text-slate-400">
                    {JSON.stringify(recoveryContext, null, 2)}
                  </pre>
                )}
              </div>
            </>
          )}

          {selectedTaskId && loadingDetail && !recoveryContext && (
            <div className="flex items-center justify-center py-10">
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
