"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type BucketMetric = { key: string; count: number };
type ActionMetric = { action: string; used: number; success: number; failed: number; success_rate: number };

type SummaryPayload = {
  total_recovery_incidents: number;
  currently_paused_recovery_tasks: number;
  auto_playbook_attempts: number;
  auto_playbook_success_rate: number;
  human_recovery_success_rate: number;
  candidate_playbooks_count: number;
  trusted_playbooks_count: number;
  playbooks_promoted_to_trusted: number;
  avg_pause_to_first_action_seconds: number;
  avg_pause_to_resumed_seconds: number;
  repeated_incidents_same_workflow_signature: number;
  incidents_by_workflow: BucketMetric[];
  top_problem_signatures: BucketMetric[];
  top_last_error_patterns: BucketMetric[];
  most_used_manual_actions: ActionMetric[];
  most_successful_manual_actions: ActionMetric[];
};

type IncidentData = {
  incidents_by_workflow: BucketMetric[];
  incidents_by_signature: BucketMetric[];
  incidents_over_time: BucketMetric[];
  rows: Array<{
    task_id?: string;
    workflow_name?: string;
    machine_uuid?: string;
    status?: string;
    problem_signature?: string;
    updated_at?: string;
    manual_action_count?: number;
    auto_failed_before_human?: boolean;
  }>;
};

type ActionData = {
  manual_action_usage: ActionMetric[];
  manual_action_success: ActionMetric[];
  suggested_vs_chosen: Array<{ action: string; recommended: number; chosen: number }>;
};

type PlaybookData = {
  top_performing_trusted_playbooks: Array<{
    playbook_id: string;
    workflow_name: string;
    success_rate: number;
    attempted_count: number;
    confidence_score: number;
    status: string;
  }>;
  candidate_playbooks_nearing_trust: Array<{
    playbook_id: string;
    workflow_name: string;
    success_count: number;
    confidence_score: number;
  }>;
};

type TimelineData = {
  recent_events: Array<{
    task_id?: string;
    workflow_name?: string;
    event_type?: string;
    timestamp?: string;
  }>;
  recent_failed_self_healing_attempts: Array<{
    task_id?: string;
    workflow_name?: string;
    event_type?: string;
    timestamp?: string;
  }>;
};

const BUTTON_SECONDARY =
  "rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-200 transition-colors hover:border-slate-600 hover:bg-slate-800 active:scale-[.97] disabled:pointer-events-none disabled:opacity-40";

const INPUT_CLASS =
  "rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs text-slate-200 placeholder-slate-500 focus:border-cyan-500/50 focus:outline-none";

function pct(v: number): string {
  return `${(Number(v || 0) * 100).toFixed(1)}%`;
}

function sec(v: number): string {
  return `${Math.round(Number(v || 0))}s`;
}

function ago(iso?: string): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`;
  return `${Math.floor(ms / 3_600_000)}h ago`;
}

function actionLabel(action: string): string {
  return action.replace(/_/g, " ");
}

interface RecoveryAnalyticsPanelProps {
  apiBase: string;
}

export default function RecoveryAnalyticsPanel({ apiBase }: RecoveryAnalyticsPanelProps) {
  const [workflowFilter, setWorkflowFilter] = useState("");
  const [machineFilter, setMachineFilter] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [playbookStatus, setPlaybookStatus] = useState("");

  const [summary, setSummary] = useState<SummaryPayload | null>(null);
  const [incidents, setIncidents] = useState<IncidentData | null>(null);
  const [actions, setActions] = useState<ActionData | null>(null);
  const [playbooks, setPlaybooks] = useState<PlaybookData | null>(null);
  const [timeline, setTimeline] = useState<TimelineData | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (workflowFilter) p.set("workflow_name", workflowFilter);
    if (machineFilter) p.set("machine_uuid", machineFilter);
    if (startDate) p.set("start_date", new Date(startDate).toISOString());
    if (endDate) p.set("end_date", new Date(endDate).toISOString());
    if (playbookStatus) p.set("playbook_status", playbookStatus);
    return p.toString();
  }, [workflowFilter, machineFilter, startDate, endDate, playbookStatus]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const suffix = query ? `?${query}` : "";
      const [s, i, a, p, t] = await Promise.all([
        fetch(`${apiBase}/api/recovery-analytics/summary${suffix}`, { cache: "no-store" }),
        fetch(`${apiBase}/api/recovery-analytics/incidents${suffix}`, { cache: "no-store" }),
        fetch(`${apiBase}/api/recovery-analytics/actions${suffix}`, { cache: "no-store" }),
        fetch(`${apiBase}/api/recovery-analytics/playbooks${suffix}`, { cache: "no-store" }),
        fetch(`${apiBase}/api/recovery-analytics/timeline${suffix}`, { cache: "no-store" }),
      ]);

      if (!s.ok || !i.ok || !a.ok || !p.ok || !t.ok) {
        throw new Error(`Analytics request failed (${s.status}/${i.status}/${a.status}/${p.status}/${t.status})`);
      }

      const sJson = await s.json();
      const iJson = await i.json();
      const aJson = await a.json();
      const pJson = await p.json();
      const tJson = await t.json();

      setSummary((sJson?.summary ?? null) as SummaryPayload | null);
      setIncidents((iJson?.data ?? null) as IncidentData | null);
      setActions((aJson?.data ?? null) as ActionData | null);
      setPlaybooks((pJson?.data ?? null) as PlaybookData | null);
      setTimeline((tJson?.data ?? null) as TimelineData | null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, [apiBase, query]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const applySignatureFilter = (signature: string) => {
    setWorkflowFilter(signature.split("|")[0] ?? "");
  };

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 shadow-lg shadow-black/25">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-100">Recovery Analytics</h2>
          <p className="text-xs text-slate-400">Operational metrics for incidents, actions, self-healing, and playbooks.</p>
        </div>
        <button onClick={() => void loadAll()} disabled={loading} className={BUTTON_SECONDARY}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-2 xl:grid-cols-5">
        <input
          className={INPUT_CLASS}
          placeholder="Workflow"
          value={workflowFilter}
          onChange={(e) => setWorkflowFilter(e.target.value)}
        />
        <input
          className={INPUT_CLASS}
          placeholder="Machine UUID"
          value={machineFilter}
          onChange={(e) => setMachineFilter(e.target.value)}
        />
        <input className={INPUT_CLASS} type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        <input className={INPUT_CLASS} type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        <select className={INPUT_CLASS} value={playbookStatus} onChange={(e) => setPlaybookStatus(e.target.value)}>
          <option value="">Playbook status</option>
          <option value="candidate">candidate</option>
          <option value="trusted">trusted</option>
          <option value="disabled">disabled</option>
        </select>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error}
        </div>
      )}

      {!summary && !loading && !error && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-6 text-center text-sm text-slate-500">
          No analytics data yet.
        </div>
      )}

      {summary && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 xl:grid-cols-6">
            <article className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-[11px] text-slate-500">Incidents</p><p className="text-lg font-semibold text-slate-100">{summary.total_recovery_incidents}</p></article>
            <article className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-[11px] text-slate-500">Paused Now</p><p className="text-lg font-semibold text-violet-300">{summary.currently_paused_recovery_tasks}</p></article>
            <article className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-[11px] text-slate-500">Auto Success</p><p className="text-lg font-semibold text-cyan-300">{pct(summary.auto_playbook_success_rate)}</p></article>
            <article className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-[11px] text-slate-500">Human Success</p><p className="text-lg font-semibold text-emerald-300">{pct(summary.human_recovery_success_rate)}</p></article>
            <article className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-[11px] text-slate-500">Avg Pause → First Action</p><p className="text-lg font-semibold text-slate-100">{sec(summary.avg_pause_to_first_action_seconds)}</p></article>
            <article className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-[11px] text-slate-500">Avg Pause → Resume</p><p className="text-lg font-semibold text-slate-100">{sec(summary.avg_pause_to_resumed_seconds)}</p></article>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <h3 className="mb-2 text-sm font-medium text-slate-200">Incidents by Workflow</h3>
              <div className="space-y-1.5">
                {(summary.incidents_by_workflow ?? []).slice(0, 8).map((item) => (
                  <button
                    key={`wf-${item.key}`}
                    onClick={() => setWorkflowFilter(item.key)}
                    className="flex w-full items-center justify-between rounded border border-slate-800 bg-slate-950 px-2 py-1 text-left text-xs hover:border-cyan-500/30"
                  >
                    <span className="text-slate-300 truncate">{item.key}</span>
                    <span className="font-mono text-slate-400">{item.count}</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <h3 className="mb-2 text-sm font-medium text-slate-200">Top Issue Signatures</h3>
              <div className="space-y-1.5">
                {(summary.top_problem_signatures ?? []).slice(0, 8).map((item) => (
                  <button
                    key={`sig-${item.key}`}
                    onClick={() => applySignatureFilter(item.key)}
                    className="flex w-full items-center justify-between rounded border border-slate-800 bg-slate-950 px-2 py-1 text-left text-xs hover:border-cyan-500/30"
                  >
                    <span className="text-slate-300 truncate">{item.key}</span>
                    <span className="font-mono text-slate-400">{item.count}</span>
                  </button>
                ))}
              </div>
            </section>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <h3 className="mb-2 text-sm font-medium text-slate-200">Action Usage / Success</h3>
              <div className="max-h-52 space-y-1 overflow-auto pr-1">
                {(actions?.manual_action_usage ?? summary.most_used_manual_actions ?? []).slice(0, 10).map((item) => (
                  <div key={`action-${item.action}`} className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs">
                    <p className="text-slate-300">{actionLabel(item.action)}</p>
                    <p className="text-slate-500">used {item.used} · success {pct(item.success_rate)}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <h3 className="mb-2 text-sm font-medium text-slate-200">Playbook Performance</h3>
              <div className="max-h-52 space-y-1 overflow-auto pr-1">
                {(playbooks?.top_performing_trusted_playbooks ?? []).slice(0, 10).map((pb) => (
                  <div key={`pb-${pb.playbook_id}`} className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs">
                    <p className="truncate text-slate-300">{pb.workflow_name} · ...{pb.playbook_id.slice(-8)}</p>
                    <p className="text-slate-500">{pb.status} · success {pct(pb.success_rate)} · used {pb.attempted_count}</p>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <h3 className="mb-2 text-sm font-medium text-slate-200">Recent Incidents</h3>
              <div className="max-h-56 space-y-1 overflow-auto pr-1">
                {(incidents?.rows ?? []).slice(0, 20).map((row) => (
                  <div key={`row-${row.task_id}`} className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs">
                    <p className="text-slate-300">{row.workflow_name} · ...{String(row.task_id ?? "").slice(-8)}</p>
                    <p className="text-slate-500">{row.problem_signature} · {row.status} · {ago(row.updated_at)}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <h3 className="mb-2 text-sm font-medium text-slate-200">Failed Self-Healing Attempts</h3>
              <div className="max-h-56 space-y-1 overflow-auto pr-1">
                {(timeline?.recent_failed_self_healing_attempts ?? []).slice(0, 20).map((event, idx) => (
                  <div key={`fail-${idx}`} className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs">
                    <p className="text-slate-300">{event.event_type?.replace(/_/g, " ")} · ...{String(event.task_id ?? "").slice(-8)}</p>
                    <p className="text-slate-500">{event.workflow_name} · {ago(event.timestamp)}</p>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>
      )}
    </section>
  );
}
