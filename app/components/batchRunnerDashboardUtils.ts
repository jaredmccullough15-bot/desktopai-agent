export type BatchSummary = {
  total_rows?: number;
  pending_rows?: number;
  running_rows?: number;
  completed_rows?: number;
  failed_rows?: number;
  needs_review_rows?: number;
  skipped_rows?: number;
  good_no_action_needed_rows?: number;
  bad_payment_task_created_rows?: number;
  progress_percent?: number;
  estimated_remaining_seconds?: number | null;
};

export function formatEta(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return "Calculating...";
  }
  if (seconds <= 0) {
    return "0m";
  }

  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

export function isTerminalBatchStatus(status: string | null | undefined): boolean {
  const normalized = String(status || "").trim().toLowerCase();
  return ["completed", "completed_with_errors", "failed", "canceled"].includes(normalized);
}

export function safeProgressPercent(summary: BatchSummary | null | undefined): number {
  const value = Number(summary?.progress_percent ?? 0);
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function batchStatusBadgeClass(status: string | null | undefined): string {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "completed") {
    return "border border-emerald-400/30 bg-emerald-500/10 text-emerald-200";
  }
  if (normalized === "completed_with_errors") {
    return "border border-amber-400/30 bg-amber-500/10 text-amber-200";
  }
  if (normalized === "running") {
    return "border border-sky-400/30 bg-sky-500/10 text-sky-200";
  }
  if (normalized === "failed") {
    return "border border-rose-400/30 bg-rose-500/10 text-rose-200";
  }
  if (normalized === "canceled") {
    return "border border-slate-500/40 bg-slate-500/20 text-slate-200";
  }
  return "border border-slate-600/50 bg-slate-800/60 text-slate-200";
}
