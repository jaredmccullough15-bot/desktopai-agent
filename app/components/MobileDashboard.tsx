"use client";

import AlertsPanel, { type AlertItem, type HelpTask } from "./AlertsPanel";
import type { MobileView } from "./MobileNav";

// ── Minimal prop types (subset of page.tsx local types) ──────────────────────

type MobileTask = {
  id?: string;
  status?: string;
  payload?: { task_type?: string; [key: string]: unknown };
  error?: string | null;
  created_at?: string;
};

type MobileWorker = {
  machine_uuid?: string;
  machine_name?: string;
  worker_name?: string;
  status?: string;
  online?: boolean;
  current_task_id?: string | null;
};

type ChatEntry = {
  role: string;
  message: string;
  suggestedNextAction?: string;
};

export interface MobileDashboardProps {
  mobileView: MobileView;
  onNavigate: (v: MobileView) => void;

  // System state
  health: { status?: string } | null;
  machines: MobileWorker[];
  activeTasks: MobileTask[];
  failedTasks: MobileTask[];
  successfulTasks: MobileTask[];
  humanHelpTasks: HelpTask[];
  alerts: AlertItem[];
  resolveBusyKey: string | null;
  notificationPermission: NotificationPermission | "unsupported";

  // Chat / Ask Bill
  chatInput: string;
  setChatInput: (v: string) => void;
  chatHistory: ChatEntry[];
  chatLoading: boolean;
  onSendCommand: () => void;

  // Voice
  voiceSupported: boolean;
  isListening: boolean;
  isSpeaking: boolean;
  ttsEnabled: boolean;
  setTtsEnabled: (v: boolean) => void;
  startListening: () => void;
  stopListening: () => void;

  // Actions
  onRetry: (task: MobileTask) => void;
  onResolve: (taskId: string) => void;
  onClearAlert: (alertId: string) => void;
  onClearAll: () => void;
  onRequestNotifications: () => void;
}

// ── Inline helpers ────────────────────────────────────────────────────────────

function workerColor(w: MobileWorker): string {
  if (!w.online) return "bg-slate-700/60 text-slate-300 border border-slate-600/80";
  const s = (w.status ?? "").toLowerCase();
  if (s === "busy" || s === "running") return "bg-amber-500/15 text-amber-200 border border-amber-400/30";
  if (s === "idle") return "bg-emerald-500/15 text-emerald-200 border border-emerald-400/30";
  return "bg-sky-500/15 text-sky-200 border border-sky-400/30";
}

function workerLabel(w: MobileWorker): string {
  if (!w.online) return "Offline";
  const s = (w.status ?? "").toLowerCase();
  if (s === "idle") return "Idle";
  if (s === "busy" || s === "running") return "Busy";
  return w.status ?? "Online";
}

function shortId(id?: string | null): string {
  if (!id) return "—";
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

function timeAgo(ts?: string): string {
  if (!ts) return "";
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  return `${Math.floor(diff / 3_600_000)}h ago`;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function MobileDashboard({
  mobileView,
  onNavigate,
  health,
  machines,
  activeTasks,
  failedTasks,
  successfulTasks,
  humanHelpTasks,
  alerts,
  resolveBusyKey,
  notificationPermission,
  chatInput,
  setChatInput,
  chatHistory,
  chatLoading,
  onSendCommand,
  voiceSupported,
  isListening,
  isSpeaking,
  ttsEnabled,
  setTtsEnabled,
  startListening,
  stopListening,
  onRetry,
  onResolve,
  onClearAlert,
  onClearAll,
  onRequestNotifications,
}: MobileDashboardProps) {
  const urgentCount = humanHelpTasks.length + failedTasks.length;
  const isOnline = health?.status === "ok";

  return (
    <div className="min-h-[calc(100vh-4rem)] pb-2" style={{ paddingTop: "env(safe-area-inset-top)" }}>

      {/* ── Compact status bar ─────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-800/80 bg-slate-950/95 px-4 py-3 backdrop-blur-md">
        <div className="flex items-center gap-2.5">
          <span
            className={`h-2.5 w-2.5 rounded-full ${isOnline ? "bg-emerald-400 shadow-[0_0_8px_#34d399]" : "bg-rose-500 shadow-[0_0_8px_#f43f5e]"}`}
          />
          <span className="text-sm font-semibold text-slate-100">Bill</span>
          <span className="text-[11px] text-slate-500">{isOnline ? "Online" : "Offline"}</span>
        </div>
        {urgentCount > 0 && (
          <button
            type="button"
            onClick={() => onNavigate("actions")}
            className="flex animate-pulse items-center gap-1.5 rounded-full border border-rose-500/40 bg-rose-500/10 px-3 py-1 text-xs font-medium text-rose-200"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
            {urgentCount} need{urgentCount !== 1 ? "" : "s"} you
          </button>
        )}
      </header>

      {/* ══════════════════════════════════════════════════════════════════════
          STATUS VIEW — What is running, what failed, worker health at a glance
          ══════════════════════════════════════════════════════════════════════ */}
      {mobileView === "status" && (
        <div className="space-y-4 p-4">

          {/* Three key counters */}
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-xl border border-slate-800/80 bg-slate-900/80 p-3 text-center">
              <p className="text-2xl font-bold text-cyan-300">{activeTasks.length}</p>
              <p className="mt-0.5 text-[11px] text-slate-500">Running</p>
            </div>
            <div className={`rounded-xl border p-3 text-center ${failedTasks.length > 0 ? "border-rose-500/30 bg-rose-500/5" : "border-slate-800/80 bg-slate-900/80"}`}>
              <p className={`text-2xl font-bold ${failedTasks.length > 0 ? "text-rose-300" : "text-slate-600"}`}>
                {failedTasks.length}
              </p>
              <p className="mt-0.5 text-[11px] text-slate-500">Failed</p>
            </div>
            <div className="rounded-xl border border-slate-800/80 bg-slate-900/80 p-3 text-center">
              <p className="text-2xl font-bold text-emerald-300">{successfulTasks.length}</p>
              <p className="mt-0.5 text-[11px] text-slate-500">Done</p>
            </div>
          </div>

          {/* Attention banners — tap to jump to Actions */}
          {humanHelpTasks.length > 0 && (
            <button
              type="button"
              onClick={() => onNavigate("actions")}
              className="w-full rounded-xl border border-violet-500/40 bg-violet-500/8 p-3 text-left transition hover:bg-violet-500/12"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-violet-400" />
                  <span className="text-sm font-medium text-violet-200">
                    {humanHelpTasks.length} task{humanHelpTasks.length !== 1 ? "s" : ""} need your decision
                  </span>
                </div>
                <span className="text-xs text-violet-400">→</span>
              </div>
            </button>
          )}

          {failedTasks.length > 0 && (
            <button
              type="button"
              onClick={() => onNavigate("actions")}
              className="w-full rounded-xl border border-rose-500/30 bg-rose-500/5 p-3 text-left transition hover:bg-rose-500/10"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-rose-400" />
                  <span className="text-sm font-medium text-rose-200">
                    {failedTasks.length} failed task{failedTasks.length !== 1 ? "s" : ""} — tap to retry
                  </span>
                </div>
                <span className="text-xs text-rose-400">→</span>
              </div>
            </button>
          )}

          {/* Worker status */}
          <div className="rounded-xl border border-slate-800/80 bg-slate-900/80 p-4">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Workers</h3>
            {machines.length === 0 ? (
              <p className="text-sm text-slate-500">No workers connected</p>
            ) : (
              <div className="space-y-2.5">
                {machines.map((machine, i) => (
                  <div key={machine.machine_uuid ?? `w-${i}`} className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <span className="truncate text-sm text-slate-200">
                        {machine.machine_name ?? machine.worker_name ?? "Worker"}
                      </span>
                      {machine.current_task_id && (
                        <p className="truncate text-[11px] text-slate-500">
                          Running: {shortId(machine.current_task_id)}
                        </p>
                      )}
                    </div>
                    <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[11px] ${workerColor(machine)}`}>
                      {workerLabel(machine)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Active tasks feed */}
          {activeTasks.length > 0 && (
            <div className="rounded-xl border border-slate-800/80 bg-slate-900/80 p-4">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Running Now</h3>
              <div className="space-y-2.5">
                {activeTasks.slice(0, 5).map((task) => (
                  <div key={task.id} className="flex items-center gap-2.5">
                    <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-cyan-400" />
                    <span className="flex-1 truncate text-sm text-slate-200">
                      {task.payload?.task_type ?? shortId(task.id)}
                    </span>
                    {task.created_at && (
                      <span className="shrink-0 text-[11px] text-slate-500">{timeAgo(task.created_at)}</span>
                    )}
                  </div>
                ))}
                {activeTasks.length > 5 && (
                  <p className="text-[11px] text-slate-500">+{activeTasks.length - 5} more running</p>
                )}
              </div>
            </div>
          )}

          {/* All clear */}
          {activeTasks.length === 0 && failedTasks.length === 0 && humanHelpTasks.length === 0 && (
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-5 text-center">
              <p className="text-lg text-emerald-300">All clear</p>
              <p className="mt-1 text-xs text-slate-500">No active or failed tasks</p>
            </div>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          ALERTS VIEW — Historical alert feed (not actionable items)
          ══════════════════════════════════════════════════════════════════════ */}
      {mobileView === "alerts" && (
        <div className="p-4">
          <AlertsPanel
            alerts={alerts}
            humanHelpTasks={humanHelpTasks}
            onResolve={onResolve}
            onRetry={(taskId, payload) => onRetry({ id: taskId, status: "failed", payload })}
            onClearAlert={onClearAlert}
            onClearAll={onClearAll}
            resolveBusyKey={resolveBusyKey}
            onRequestNotifications={onRequestNotifications}
            notificationPermission={notificationPermission}
          />
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          ACTIONS VIEW — What needs your attention + quick response buttons
          ══════════════════════════════════════════════════════════════════════ */}
      {mobileView === "actions" && (
        <div className="space-y-4 p-4">
          {humanHelpTasks.length === 0 && failedTasks.length === 0 ? (
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-8 text-center">
              <p className="text-2xl font-light text-emerald-300">✓</p>
              <p className="mt-2 font-semibold text-emerald-300">Nothing to do</p>
              <p className="mt-1 text-xs text-slate-500">No failed tasks or decisions needed</p>
            </div>
          ) : (
            <>
              {/* Needs human decision */}
              {humanHelpTasks.length > 0 && (
                <div className="rounded-xl border border-violet-500/30 bg-slate-900/80 p-4">
                  <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-violet-300">
                    Needs Your Decision ({humanHelpTasks.length})
                  </h3>
                  <div className="space-y-3">
                    {humanHelpTasks.map((task) => (
                      <div key={task.id} className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-3">
                        <p className="mb-0.5 truncate text-sm font-medium text-slate-100">
                          {task.workflow_name ?? "Unknown workflow"}
                        </p>
                        <p className="mb-2 text-[11px] text-slate-500">{shortId(task.id)}</p>
                        {task.error && (
                          <p className="mb-2 line-clamp-2 text-xs text-rose-300">{task.error}</p>
                        )}
                        {task.recovery_last_action && (
                          <p className="mb-2 text-[11px] text-amber-300">
                            Last recovery: {task.recovery_last_action}
                          </p>
                        )}
                        <button
                          type="button"
                          onClick={() => onResolve(task.id)}
                          disabled={resolveBusyKey === task.id}
                          className="w-full rounded-lg bg-violet-600 px-3 py-2.5 text-sm font-semibold text-white shadow shadow-violet-900/40 transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {resolveBusyKey === task.id ? "Resolving…" : "Mark Resolved"}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Failed tasks */}
              {failedTasks.length > 0 && (
                <div className="rounded-xl border border-rose-500/20 bg-slate-900/80 p-4">
                  <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-rose-300">
                    Failed Tasks ({failedTasks.length})
                  </h3>
                  <div className="space-y-3">
                    {failedTasks.slice(0, 10).map((task) => (
                      <div key={task.id} className="rounded-lg border border-rose-500/15 bg-rose-500/5 p-3">
                        <p className="mb-0.5 truncate text-sm font-medium text-slate-100">
                          {task.payload?.task_type ?? "Unknown task"}
                        </p>
                        <p className="mb-2 text-[11px] text-slate-500">{shortId(task.id)}</p>
                        {task.error && (
                          <p className="mb-2 line-clamp-2 text-xs text-rose-300">{task.error}</p>
                        )}
                        <button
                          type="button"
                          onClick={() => onRetry(task)}
                          className="w-full rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2.5 text-sm font-semibold text-rose-200 transition hover:bg-rose-500/20"
                        >
                          Retry
                        </button>
                      </div>
                    ))}
                    {failedTasks.length > 10 && (
                      <p className="text-center text-xs text-slate-500">
                        +{failedTasks.length - 10} more — use desktop for full list
                      </p>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          ASK BILL VIEW — Simple commands and status queries
          ══════════════════════════════════════════════════════════════════════ */}
      {mobileView === "ask" && (
        <div className="flex flex-col gap-4 p-4">

          {/* Chat history (last 6 messages) */}
          {chatHistory.length > 0 ? (
            <div className="max-h-[45vh] space-y-3 overflow-y-auto">
              {chatHistory.slice(-6).map((entry, i) => (
                <div
                  key={`msg-${i}`}
                  className={
                    entry.role === "user"
                      ? "ml-8 rounded-xl border border-cyan-500/30 bg-cyan-500/8 p-3"
                      : "mr-8 rounded-xl border border-slate-700/80 bg-slate-900/90 p-3"
                  }
                >
                  <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
                    {entry.role === "user" ? "You" : "Bill"}
                  </p>
                  <p className="text-sm leading-relaxed text-slate-100">{entry.message}</p>
                  {entry.suggestedNextAction && (
                    <p className="mt-2 rounded-lg border border-cyan-400/20 bg-cyan-500/8 px-2.5 py-1.5 text-xs text-cyan-200">
                      {entry.suggestedNextAction}
                    </p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            /* Quick-start prompts */
            <div className="rounded-xl border border-slate-800/80 bg-slate-900/60 p-4">
              <p className="mb-1 text-sm font-medium text-slate-300">Ask Bill anything</p>
              <p className="mb-3 text-xs text-slate-500">Status, commands, or questions about your workers and tasks.</p>
              <div className="flex flex-wrap gap-2">
                {[
                  "What's running?",
                  "What failed?",
                  "Which worker is free?",
                  "Retry last failure",
                  "Summarize status",
                ].map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => setChatInput(prompt)}
                    className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-400 transition hover:border-cyan-400/50 hover:text-cyan-300"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Input */}
          <div className="rounded-xl border border-cyan-500/20 bg-slate-900/80 p-3 shadow-inner shadow-cyan-950/30">
            <textarea
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSendCommand();
                }
              }}
              rows={3}
              placeholder="Ask Bill or give a command…"
              className="w-full resize-none rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-500/30"
            />
            <div className="mt-2 flex items-center gap-2">
              {voiceSupported && (
                <button
                  type="button"
                  onClick={isListening ? stopListening : startListening}
                  title={isListening ? "Stop listening" : "Speak command"}
                  className={`rounded-lg p-2 transition ${
                    isListening
                      ? "animate-pulse bg-rose-500 text-white"
                      : "border border-slate-700 bg-slate-900 text-slate-400 hover:border-cyan-400/50 hover:text-cyan-300"
                  }`}
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                  </svg>
                </button>
              )}
              <button
                type="button"
                onClick={() => setTtsEnabled(!ttsEnabled)}
                title={ttsEnabled ? "Mute Bill's voice" : "Enable Bill's voice"}
                className={`rounded-lg p-2 transition ${
                  ttsEnabled
                    ? "border border-cyan-400/40 bg-cyan-500/15 text-cyan-300"
                    : "border border-slate-700 bg-slate-900 text-slate-600 hover:text-slate-400"
                }`}
              >
                {isSpeaking ? (
                  <svg className="h-4 w-4 animate-pulse" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.536 8.464a5 5 0 010 7.072M12 6v12m3-9a3 3 0 010 6" />
                  </svg>
                ) : (
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11 5L6 9H2v6h4l5 4V5z" />
                    {ttsEnabled && <path strokeLinecap="round" strokeLinejoin="round" d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07" />}
                  </svg>
                )}
              </button>
              <button
                type="button"
                onClick={onSendCommand}
                disabled={chatLoading || !chatInput.trim()}
                className="ml-auto rounded-lg bg-cyan-500 px-5 py-2 text-sm font-semibold text-slate-950 shadow shadow-cyan-500/20 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {chatLoading ? "…" : "Send"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
