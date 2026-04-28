"use client";

import { BillLogo } from "./BillLogo";

interface MetricCardProps {
  label: string;
  value: number | string;
  color?: "cyan" | "green" | "amber" | "red";
  icon?: React.ReactNode;
}

function MetricCard({ label, value, color = "cyan", icon }: MetricCardProps) {
  const valueClass =
    color === "green"
      ? "text-emerald-300"
      : color === "amber"
        ? "text-amber-300"
        : color === "red"
          ? "text-rose-300"
          : "text-cyan-300";

  return (
    <div className="flex min-w-[100px] flex-col gap-1 rounded-xl border border-slate-800/90 bg-slate-900/90 px-4 py-3">
      <div className="flex items-center gap-1.5">
        {icon && <span className="opacity-70">{icon}</span>}
        <p className="text-[11px] text-slate-400">{label}</p>
      </div>
      <p className={`text-2xl font-semibold leading-none ${valueClass}`}>{value}</p>
    </div>
  );
}

interface BillHeaderProps {
  workersOnline: number;
  activeTasks: number;
  needsAttention: number;
  failedTasks: number;
  completed24h: number;
}

export function BillHeader({
  workersOnline,
  activeTasks,
  needsAttention,
  failedTasks,
  completed24h,
}: BillHeaderProps) {
  return (
    <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <BillLogo />

      {/* Metric bar */}
      <div className="flex flex-wrap gap-2">
        <MetricCard
          label="Workers Online"
          value={workersOnline}
          color="green"
          icon={
            <svg className="h-3.5 w-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <circle cx="9" cy="7" r="4" />
              <path strokeLinecap="round" d="M3 21v-2a4 4 0 014-4h4a4 4 0 014 4v2" />
              <path strokeLinecap="round" d="M16 3.13a4 4 0 010 7.75" />
              <path strokeLinecap="round" d="M21 21v-2a4 4 0 00-3-3.87" />
            </svg>
          }
        />
        <MetricCard
          label="Active Tasks"
          value={activeTasks}
          color="cyan"
          icon={
            <svg className="h-3.5 w-3.5 text-cyan-400" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5.14v14l11-7-11-7z" />
            </svg>
          }
        />
        <MetricCard
          label="Needs Attention"
          value={needsAttention}
          color="amber"
          icon={
            <svg className="h-3.5 w-3.5 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            </svg>
          }
        />
        <MetricCard
          label="Failed Tasks"
          value={failedTasks}
          color="red"
          icon={
            <svg className="h-3.5 w-3.5 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <circle cx="12" cy="12" r="10" />
              <path strokeLinecap="round" d="M15 9l-6 6M9 9l6 6" />
            </svg>
          }
        />
        <MetricCard
          label="Completed (24h)"
          value={completed24h}
          color="green"
          icon={
            <svg className="h-3.5 w-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <circle cx="12" cy="12" r="10" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4" />
            </svg>
          }
        />
      </div>
    </header>
  );
}
