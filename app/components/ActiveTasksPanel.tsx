"use client";

interface Task {
  id?: string;
  status?: string;
  payload?: { task_type?: string; [key: string]: unknown };
  assigned_machine_uuid?: string | null;
  error?: string | null;
  created_at?: string;
}

interface ActiveTasksPanelProps {
  activeTasks: Task[];
  allTasks: Task[];
  taskActionBusyKey: string | null;
  onCancel: (taskId?: string) => void;
  onRetry: (task: Task) => void;
  onViewAll?: () => void;
}

function taskStatusBadge(status?: string): { label: string; cls: string } {
  const s = (status ?? "").toLowerCase();
  if (s === "running")
    return { label: "Running", cls: "bg-sky-500/15 text-sky-200 border border-sky-400/30" };
  if (s === "queued")
    return { label: "Queued", cls: "bg-amber-500/15 text-amber-200 border border-amber-400/30" };
  if (s === "assigned")
    return { label: "Assigned", cls: "bg-amber-500/15 text-amber-200 border border-amber-400/30" };
  if (s === "needs_human_help")
    return { label: "Approval", cls: "bg-amber-500/15 text-amber-200 border border-amber-400/30" };
  return { label: s || "Unknown", cls: "bg-slate-700/60 text-slate-300 border border-slate-600/50" };
}

function taskIcon(status?: string) {
  const s = (status ?? "").toLowerCase();
  if (s === "running") {
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-sky-400/30 bg-sky-500/15">
        <svg className="h-4 w-4 text-sky-400" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8 5.14v14l11-7-11-7z" />
        </svg>
      </div>
    );
  }
  if (s === "needs_human_help") {
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-amber-400/30 bg-amber-500/15">
        <svg className="h-4 w-4 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <rect x="6" y="4" width="4" height="16" rx="1" />
          <rect x="14" y="4" width="4" height="16" rx="1" />
        </svg>
      </div>
    );
  }
  return (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-amber-400/30 bg-amber-500/15">
      <svg className="h-4 w-4 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <circle cx="12" cy="12" r="10" />
        <path strokeLinecap="round" d="M12 8v4l3 3" />
      </svg>
    </div>
  );
}

function timeSince(dateStr?: string): string {
  if (!dateStr) return "";
  const ms = Date.now() - new Date(dateStr).getTime();
  if (isNaN(ms)) return "";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

function shortWorker(uuid?: string | null): string {
  if (!uuid) return "";
  return uuid.length > 12 ? uuid.slice(0, 8) + "…" : uuid;
}

export function ActiveTasksPanel({
  activeTasks,
  taskActionBusyKey,
  onCancel,
  onViewAll,
}: ActiveTasksPanelProps) {
  const shown = activeTasks.slice(0, 5);

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-lg">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-50">Active Tasks</h2>
        {activeTasks.length > 5 && (
          <button
            type="button"
            onClick={onViewAll}
            className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-400 transition hover:border-cyan-400/50 hover:text-cyan-200"
          >
            View All
          </button>
        )}
      </div>

      {shown.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-500">No active tasks right now.</p>
      ) : (
        <div className="space-y-2">
          {shown.map((task, idx) => {
            const badge = taskStatusBadge(task.status);
            const workerLabel = shortWorker(task.assigned_machine_uuid);
            const elapsed = timeSince(task.created_at);
            const meta = [workerLabel, elapsed ? `${elapsed}` : ""].filter(Boolean).join(" · ");
            const canCancel = !!task.id && ["queued", "assigned", "running"].includes(
              (task.status ?? "").toLowerCase()
            );

            return (
              <div
                key={task.id ?? `active-${idx}`}
                className="flex items-start gap-3 rounded-xl border border-slate-800/80 bg-slate-900/60 p-3"
              >
                {taskIcon(task.status)}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-100">
                    {task.payload?.task_type ?? "Task"}
                  </p>
                  {meta && <p className="mt-0.5 text-[11px] text-slate-500">{meta}</p>}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${badge.cls}`}>
                    {badge.label}
                  </span>
                  {canCancel && (
                    <button
                      type="button"
                      disabled={taskActionBusyKey !== null}
                      onClick={() => onCancel(task.id)}
                      className="rounded p-1 text-slate-600 transition hover:text-rose-400 disabled:opacity-40"
                      title="Cancel task"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <button
        type="button"
        onClick={onViewAll}
        className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-slate-700/80 bg-slate-900/60 py-2.5 text-xs font-medium text-slate-300 transition hover:border-cyan-400/50 hover:text-cyan-200"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h8" />
        </svg>
        View All Tasks
      </button>
    </section>
  );
}
