"use client";

interface SystemHealthFooterProps {
  healthy: boolean;
  statusText: string;
  coreVersion: string;
  lastUpdated: Date;
  onRefresh: () => void;
}

function timeAgo(d: Date): string {
  const s = Math.floor((Date.now() - d.getTime()) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  return `${Math.floor(s / 60)}m ago`;
}

export function SystemHealthFooter({
  healthy,
  statusText,
  coreVersion,
  lastUpdated,
  onRefresh,
}: SystemHealthFooterProps) {
  return (
    <footer className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-800 bg-slate-900/80 px-5 py-3 text-xs text-slate-400">
      {/* Left: health */}
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${healthy ? "bg-emerald-400" : "bg-rose-400"}`} />
        <span className={healthy ? "font-medium text-emerald-300" : "font-medium text-rose-300"}>
          {healthy ? "System Healthy" : "System Issue"}
        </span>
        <span className="text-slate-500">·</span>
        <span>{statusText}</span>
      </div>

      {/* Center: version */}
      <span className="text-slate-500">Bill Core {coreVersion}</span>

      {/* Right: last updated + refresh */}
      <div className="flex items-center gap-2">
        <span>Last updated: {timeAgo(lastUpdated)}</span>
        <button
          type="button"
          onClick={onRefresh}
          title="Refresh dashboard"
          className="rounded p-1 text-slate-500 transition hover:text-cyan-300"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>
    </footer>
  );
}
