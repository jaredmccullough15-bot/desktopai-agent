"use client";

import { type Dispatch, type SetStateAction } from "react";

interface Machine {
  machine_uuid?: string;
  machine_name?: string;
  worker_name?: string;
  status?: string;
  worker_version?: string;
  online?: boolean;
  last_seen?: string;
  current_task_id?: string | null;
}

interface WorkersPanelProps {
  machines: Machine[];
  onlineCount: number;
  targetMachineUuid: string;
  setTargetMachineUuid: Dispatch<SetStateAction<string>>;
  renamingMachineUuid: string | null;
  setRenamingMachineUuid: Dispatch<SetStateAction<string | null>>;
  renameValue: string;
  setRenameValue: Dispatch<SetStateAction<string>>;
  onRename: (uuid: string, name: string) => void;
  onDelete: (uuid: string) => void;
  machinesError?: string;
}

function workerStatusText(machine: Machine): string {
  if (!machine.online) return "Offline";
  const s = (machine.status ?? "").toLowerCase();
  if (s === "idle") return "Online · Idle";
  if (s === "busy" || s === "running") return "Online · Busy";
  return `Online`;
}

function workerStatusBadge(machine: Machine): string {
  if (!machine.online)
    return "bg-slate-700/60 text-slate-400 border border-slate-600/80";
  const s = (machine.status ?? "").toLowerCase();
  if (s === "busy" || s === "running")
    return "bg-amber-500/15 text-amber-200 border border-amber-400/30";
  return "bg-emerald-500/15 text-emerald-300 border border-emerald-400/30";
}

function timeSince(dateStr?: string): string {
  if (!dateStr) return "–";
  const ms = Date.now() - new Date(dateStr).getTime();
  if (isNaN(ms)) return "–";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

function activeTaskCount(machine: Machine): number {
  return machine.current_task_id ? 1 : 0;
}

export function WorkersPanel({
  machines,
  onlineCount,
  targetMachineUuid,
  setTargetMachineUuid,
  renamingMachineUuid,
  setRenamingMachineUuid,
  renameValue,
  setRenameValue,
  onRename,
  onDelete,
  machinesError,
}: WorkersPanelProps) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-lg">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-50">Workers</h2>
        <span className="flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          {onlineCount} Online
        </span>
      </div>

      {machinesError ? (
        <p className="text-sm text-rose-300">{machinesError}</p>
      ) : machines.length === 0 ? (
        <p className="text-sm text-slate-500">No workers detected.</p>
      ) : (
        <div className="space-y-3">
          {machines.map((machine, idx) => {
            const uuid = machine.machine_uuid ?? `machine-${idx}`;
            const name = machine.machine_name ?? machine.worker_name ?? "Unknown";
            const isSelected = !!machine.machine_uuid && machine.machine_uuid === targetMachineUuid;
            const taskCnt = activeTaskCount(machine);

            return (
              <div
                key={uuid}
                className={`rounded-xl border p-3 transition ${
                  isSelected
                    ? "border-cyan-400/40 bg-slate-900"
                    : "border-slate-800 bg-slate-900/60 hover:border-slate-700"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    {/* Name row */}
                    {renamingMachineUuid === machine.machine_uuid ? (
                      <div className="flex items-center gap-1.5">
                        <input
                          autoFocus
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") onRename(machine.machine_uuid ?? "", renameValue);
                            if (e.key === "Escape") setRenamingMachineUuid(null);
                          }}
                          className="w-full rounded border border-cyan-500/50 bg-slate-800 px-2 py-1 text-sm text-slate-100 outline-none focus:ring-1 focus:ring-cyan-500/50"
                        />
                        <button
                          type="button"
                          onClick={() => onRename(machine.machine_uuid ?? "", renameValue)}
                          className="shrink-0 rounded bg-cyan-600 px-2 py-1 text-[11px] text-white hover:bg-cyan-500"
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => setRenamingMachineUuid(null)}
                          className="shrink-0 text-slate-500 hover:text-slate-300"
                        >
                          ✕
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5">
                        {/* Online dot */}
                        <span
                          className={`h-2 w-2 shrink-0 rounded-full ${machine.online ? "bg-emerald-400" : "bg-slate-600"}`}
                        />
                        <p className="truncate text-sm font-medium text-slate-100">{name}</p>
                        {machine.worker_version && (
                          <span className="shrink-0 rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">
                            {machine.worker_version}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Status + heartbeat + tasks */}
                    {renamingMachineUuid !== machine.machine_uuid && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${workerStatusBadge(machine)}`}>
                          {workerStatusText(machine)}
                        </span>
                        <span className="text-[11px] text-slate-500">
                          Last heartbeat: {timeSince(machine.last_seen)}
                        </span>
                        {taskCnt > 0 && (
                          <span className="text-[11px] text-slate-500">Active tasks: {taskCnt}</span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Monitor + action icons */}
                  {renamingMachineUuid !== machine.machine_uuid && (
                    <div className="flex shrink-0 items-center gap-1.5">
                      <button
                        type="button"
                        title="Select worker"
                        onClick={() => setTargetMachineUuid(machine.machine_uuid ?? "")}
                        className={`rounded p-1.5 transition ${
                          isSelected
                            ? "text-cyan-400"
                            : "text-slate-600 hover:text-slate-300"
                        }`}
                      >
                        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                          <rect x="2" y="3" width="20" height="14" rx="2" />
                          <path strokeLinecap="round" d="M8 21h8M12 17v4" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        title="Rename worker"
                        onClick={() => {
                          setRenamingMachineUuid(machine.machine_uuid ?? null);
                          setRenameValue(name);
                        }}
                        className="rounded p-1.5 text-slate-600 transition hover:text-slate-300"
                      >
                        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 112.828 2.828L11.828 15.828a2 2 0 01-1.414.586H9v-2a2 2 0 01.586-1.414z" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        title="Remove worker"
                        onClick={() => {
                          if (confirm(`Remove "${name}" from the list?`))
                            onDelete(machine.machine_uuid ?? "");
                        }}
                        className="rounded p-1.5 text-slate-600 transition hover:text-rose-400"
                      >
                        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4h6v3M3 7h18" />
                        </svg>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Manage workers button */}
      <button
        type="button"
        className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-900/60 py-2.5 text-xs font-medium text-slate-300 transition hover:border-cyan-400/50 hover:text-cyan-200"
        onClick={() => setTargetMachineUuid("")}
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <circle cx="9" cy="7" r="4" />
          <path strokeLinecap="round" d="M3 21v-2a4 4 0 014-4h4a4 4 0 014 4v2" />
          <path strokeLinecap="round" d="M16 3.13a4 4 0 010 7.75M21 21v-2a4 4 0 00-3-3.87" />
        </svg>
        Manage Workers
      </button>
    </section>
  );
}
