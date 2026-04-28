"use client";

import type { AlertItem } from "./AlertsPanel";

interface RecentActivityPanelProps {
  alerts: AlertItem[];
  onViewAll?: () => void;
}

function alertStatusBadge(kind: string): { label: string; cls: string } {
  switch (kind) {
    case "task_completed":
      return { label: "Completed", cls: "bg-emerald-500/15 text-emerald-300 border border-emerald-400/30" };
    case "recovering":
      return { label: "Running", cls: "bg-sky-500/15 text-sky-200 border border-sky-400/30" };
    case "needs_human":
      return { label: "Attention", cls: "bg-amber-500/15 text-amber-200 border border-amber-400/30" };
    case "task_failed":
      return { label: "Failed", cls: "bg-rose-500/15 text-rose-200 border border-rose-400/30" };
    case "worker_offline":
      return { label: "Offline", cls: "bg-slate-700/60 text-slate-300 border border-slate-600/50" };
    default:
      return { label: "Info", cls: "bg-slate-700/60 text-slate-300 border border-slate-600/50" };
  }
}

function alertIcon(kind: string) {
  switch (kind) {
    case "task_completed":
      return (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-emerald-400/30 bg-emerald-500/15">
          <svg className="h-4 w-4 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4" />
            <circle cx="12" cy="12" r="10" />
          </svg>
        </div>
      );
    case "recovering":
      return (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-sky-400/30 bg-sky-500/15">
          <svg className="h-4 w-4 text-sky-400" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5.14v14l11-7-11-7z" />
          </svg>
        </div>
      );
    case "needs_human":
      return (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-amber-400/30 bg-amber-500/15">
          <svg className="h-4 w-4 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          </svg>
        </div>
      );
    case "task_failed":
    default:
      return (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-rose-400/30 bg-rose-500/15">
          <svg className="h-4 w-4 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <circle cx="12" cy="12" r="10" />
            <path strokeLinecap="round" d="M15 9l-6 6M9 9l6 6" />
          </svg>
        </div>
      );
  }
}

function timeSince(dateStr?: string): string {
  if (!dateStr) return "";
  const ms = Date.now() - new Date(dateStr).getTime();
  if (isNaN(ms)) return "";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s} seconds ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  return `${Math.floor(m / 60)} hours ago`;
}

export function RecentActivityPanel({ alerts, onViewAll }: RecentActivityPanelProps) {
  const shown = alerts.slice(0, 6);

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-lg">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-50">Recent Activity</h2>
        {alerts.length > 6 && (
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
        <p className="py-6 text-center text-sm text-slate-500">No recent activity. Run a workflow to get started.</p>
      ) : (
        <div className="space-y-2">
          {shown.map((alert) => {
            const badge = alertStatusBadge(alert.kind);
            const meta = [
              alert.workerName,
              timeSince(alert.timestamp),
            ]
              .filter(Boolean)
              .join(" · ");

            return (
              <div
                key={alert.id}
                className="flex items-start gap-3 rounded-xl border border-slate-800/80 bg-slate-900/60 p-3"
              >
                {alertIcon(alert.kind)}
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-slate-100">{alert.title}</p>
                  {meta && <p className="mt-0.5 text-[11px] text-slate-500">{meta}</p>}
                </div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium ${badge.cls}`}>
                  {badge.label}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
