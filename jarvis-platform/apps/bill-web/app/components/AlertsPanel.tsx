"use client";

export type AlertKind = "needs_human" | "task_failed" | "worker_offline" | "recovering" | "task_completed";

export interface AlertItem {
  id: string;
  kind: AlertKind;
  title: string;
  detail: string;
  timestamp: string;
  taskId?: string;
  taskPayload?: Record<string, unknown>;
  workerName?: string;
}

export interface HelpTask {
  id: string;
  workflow_name?: string;
  error?: string;
  updated_at?: string;
  recovery_last_action?: string;
  assigned_machine_uuid?: string;
}

interface AlertsPanelProps {
  alerts: AlertItem[];
  humanHelpTasks: HelpTask[];
  onResolve: (taskId: string) => void;
  onRetry: (taskId: string, taskPayload: Record<string, unknown>) => void;
  onClearAlert: (alertId: string) => void;
  onClearAll: () => void;
  resolveBusyKey: string | null;
  onRequestNotifications: () => void;
  notificationPermission: NotificationPermission | "unsupported";
}

const kindLabel: Record<AlertKind, string> = {
  needs_human: "Needs You",
  task_failed: "Task Failed",
  worker_offline: "Worker Offline",
  recovering: "Recovering",
  task_completed: "Completed",
};

const kindClasses: Record<AlertKind, string> = {
  needs_human: "border-violet-500/40 bg-violet-500/10 text-violet-200",
  task_failed: "border-rose-500/40 bg-rose-500/10 text-rose-200",
  worker_offline: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  recovering: "border-sky-500/40 bg-sky-500/10 text-sky-200",
  task_completed: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
};

const kindDot: Record<AlertKind, string> = {
  needs_human: "bg-violet-400 animate-pulse",
  task_failed: "bg-rose-400",
  worker_offline: "bg-amber-400",
  recovering: "bg-sky-400 animate-pulse",
  task_completed: "bg-emerald-400",
};

function timeAgo(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export default function AlertsPanel({
  alerts,
  humanHelpTasks,
  onResolve,
  onRetry,
  onClearAlert,
  onClearAll,
  resolveBusyKey,
  onRequestNotifications,
  notificationPermission,
}: AlertsPanelProps) {
  const urgentCount = humanHelpTasks.length;

  return (
    <div className="space-y-4">
      {/* Notification permission request */}
      {notificationPermission === "default" && (
        <div className="flex items-center justify-between rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-4 py-3">
          <div>
            <p className="text-sm font-medium text-cyan-200">Enable push notifications</p>
            <p className="text-xs text-slate-400">Get alerted on your phone when tasks need attention.</p>
          </div>
          <button
            type="button"
            onClick={onRequestNotifications}
            className="ml-3 shrink-0 rounded-lg bg-cyan-500 px-3 py-1.5 text-xs font-medium text-slate-950 hover:bg-cyan-400"
          >
            Allow
          </button>
        </div>
      )}

      {/* Human help tasks — highest urgency */}
      {urgentCount > 0 && (
        <section>
          <div className="mb-2 flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-violet-400 animate-pulse" />
            <h3 className="text-sm font-semibold text-violet-200">Needs Your Attention ({urgentCount})</h3>
          </div>
          <div className="space-y-2">
            {humanHelpTasks.map((task) => (
              <div
                key={task.id}
                className="rounded-xl border border-violet-500/40 bg-violet-500/10 p-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-violet-100">
                      {task.workflow_name ?? "Task"} timed out
                    </p>
                    <p className="mt-0.5 text-[11px] text-slate-400 font-mono">{task.id.slice(0, 12)}…</p>
                    {task.recovery_last_action && (
                      <p className="mt-1 text-xs text-slate-400">
                        Last recovery: <span className="text-slate-300">{task.recovery_last_action}</span>
                      </p>
                    )}
                    {task.error && (
                      <p className="mt-1 line-clamp-2 text-xs text-rose-300">{task.error}</p>
                    )}
                  </div>
                  {task.updated_at && (
                    <span className="shrink-0 text-[10px] text-slate-500">{timeAgo(task.updated_at)}</span>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => onResolve(task.id)}
                    disabled={resolveBusyKey === `resolve-${task.id}`}
                    className="rounded-lg bg-violet-500 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-violet-400 disabled:opacity-50"
                  >
                    {resolveBusyKey === `resolve-${task.id}` ? "Resolving…" : "Mark Resolved"}
                  </button>
                  <button
                    type="button"
                    onClick={() => onRetry(task.id, { workflow_name: task.workflow_name })}
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-cyan-400/60 hover:text-cyan-200"
                  >
                    Retry
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Recent alerts */}
      {alerts.length > 0 ? (
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-200">Recent Alerts</h3>
            <button
              type="button"
              onClick={onClearAll}
              className="text-xs text-slate-500 hover:text-slate-300"
            >
              Clear all
            </button>
          </div>
          <div className="space-y-2">
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className={`rounded-xl border p-3 ${kindClasses[alert.kind]}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2 min-w-0">
                    <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${kindDot[alert.kind]}`} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-semibold uppercase tracking-wider opacity-80">
                          {kindLabel[alert.kind]}
                        </span>
                        <span className="text-[10px] text-slate-500">{timeAgo(alert.timestamp)}</span>
                      </div>
                      <p className="mt-0.5 text-sm font-medium">{alert.title}</p>
                      <p className="mt-0.5 text-xs opacity-75">{alert.detail}</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onClearAlert(alert.id)}
                    className="shrink-0 text-slate-600 hover:text-slate-400"
                  >
                    <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
                {alert.taskId && (alert.kind === "task_failed" || alert.kind === "recovering") && (
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      onClick={() => onRetry(alert.taskId!, alert.taskPayload ?? {})}
                      className="rounded border border-current/30 px-2.5 py-1 text-[11px] transition hover:bg-white/10"
                    >
                      Retry
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      ) : urgentCount === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full border border-emerald-400/30 bg-emerald-500/10">
            <svg className="h-6 w-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <p className="text-sm text-slate-300">All clear</p>
          <p className="mt-1 text-xs text-slate-500">No alerts right now.</p>
        </div>
      ) : null}
    </div>
  );
}
