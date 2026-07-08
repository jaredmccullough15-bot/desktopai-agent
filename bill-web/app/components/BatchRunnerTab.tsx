"use client";

import { useEffect, useMemo, useState } from "react";
import {
  batchStatusBadgeClass,
  formatEta,
  isTerminalBatchStatus,
  safeProgressPercent,
  type BatchSummary,
} from "./batchRunnerDashboardUtils";

type Machine = {
  machine_uuid?: string;
  machine_name?: string;
  status?: string;
  online?: boolean;
};

type BatchRow = {
  row_id: string;
  row_number: number;
  mapped: Record<string, string>;
  status: string;
  payment_status: "pending" | "good" | "bad" | "needs_review";
  paid_through_date?: string | null;
  task_id?: string | null;
  child_task_id?: string | null;
  child_task_status?: string | null;
  assigned_machine_uuid?: string | null;
  worker_name?: string | null;
  matched_client_name?: string | null;
  keap_task_created?: boolean;
  keap_task_id?: string | null;
  notes?: string | null;
  error?: string | null;
  completed_at?: string | null;
};

type BatchResponse = {
  batch_id: string;
  status: string;
  workflow_name: string;
  tenant_id?: string;
  filename: string;
  created_by_name?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  target_machine_uuid?: string | null;
  target_worker_name?: string | null;
  summary: BatchSummary;
  rows: BatchRow[];
};

type BatchListResponse = {
  items: BatchResponse[];
  count: number;
};

type UploadResponse = {
  batch: BatchResponse;
  mapping_validation: {
    valid: boolean;
    missing_required_fields: string[];
    invalid_mapped_fields: string[];
  };
};

type BatchRunnerTabProps = {
  machines: Machine[];
};

type RowFilterOption =
  | "all"
  | "pending"
  | "running"
  | "completed"
  | "good_no_action_needed"
  | "bad_payment_task_created"
  | "needs_review"
  | "failed"
  | "skipped";

const BTN_PRIMARY =
  "rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50";
const BTN_SECONDARY =
  "rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-cyan-400/70 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50";

export function BatchRunnerTab({ machines }: BatchRunnerTabProps) {
  const [file, setFile] = useState<File | null>(null);
  const [workflowName, setWorkflowName] = useState("CI Check - Single Client Lookup");
  const [targetMachineUuid, setTargetMachineUuid] = useState("");
  const [mappingJson, setMappingJson] = useState(
    JSON.stringify(
      {
        client_name: "client_name",
        first_name: "first_name",
        last_name: "last_name",
        dob: "dob",
        member_id: "member_id",
        policy_id: "policy_id",
        keap_id: "keap_id",
        paid_through_date: "paid_through_date",
        notes: "notes",
      },
      null,
      2,
    ),
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [errorDetail, setErrorDetail] = useState<string>("");
  const [batch, setBatch] = useState<BatchResponse | null>(null);
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [recentBatches, setRecentBatches] = useState<BatchResponse[]>([]);
  const [rowFilter, setRowFilter] = useState<RowFilterOption>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);

  const workerOptions = useMemo(
    () => machines.filter((machine) => machine.machine_uuid && machine.online),
    [machines],
  );

  const progressPercent = safeProgressPercent(batch?.summary);

  const filteredRows = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return rows.filter((row) => {
      const normalizedStatus = String(row.status || "").toLowerCase();
      const normalizedPayment = String(row.payment_status || "").toLowerCase();
      const isBadPaymentCreated = normalizedPayment === "bad" && Boolean(row.keap_task_created);

      if (rowFilter === "pending" && !(normalizedStatus === "ready" || normalizedStatus === "queued")) return false;
      if (rowFilter === "running" && !["assigned", "in_progress", "running"].includes(normalizedStatus)) return false;
      if (rowFilter === "completed" && normalizedStatus !== "completed") return false;
      if (rowFilter === "good_no_action_needed" && normalizedPayment !== "good") return false;
      if (rowFilter === "bad_payment_task_created" && !isBadPaymentCreated) return false;
      if (rowFilter === "needs_review" && normalizedPayment !== "needs_review") return false;
      if (rowFilter === "failed" && normalizedStatus !== "failed") return false;
      if (rowFilter === "skipped" && !["invalid", "skipped", "canceled"].includes(normalizedStatus)) return false;

      if (!q) return true;

      const haystack = [
        row.row_number,
        row.mapped?.client_name,
        row.mapped?.member_name,
        row.matched_client_name,
        row.keap_task_id,
        row.error,
        row.notes,
        row.mapped?.member_id,
      ]
        .map((value) => String(value || "").toLowerCase())
        .join(" ");

      return haystack.includes(q);
    });
  }, [rows, rowFilter, searchQuery]);

  const toDisplayTime = (value?: string | null): string => {
    if (!value) return "-";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
  };

  const parseErrorBody = async (response: Response): Promise<string> => {
    try {
      const text = await response.text();
      if (!text) return "";
      return text;
    } catch {
      return "";
    }
  };

  const loadRecentBatches = async () => {
    try {
      const response = await fetch("/api/proxy/batch-runs?limit=20");
      const payload = (await response.json()) as BatchListResponse | { detail?: string; error?: string };
      if (!response.ok) {
        throw new Error((payload as { detail?: string; error?: string }).detail || (payload as { detail?: string; error?: string }).error || "Failed to load recent batches");
      }
      setRecentBatches((payload as BatchListResponse).items || []);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load recent batches");
    }
  };

  const fetchBatch = async (batchId: string) => {
    const [batchResponse, rowsResponse] = await Promise.all([
      fetch(`/api/proxy/batch-runs/${batchId}`),
      fetch(`/api/proxy/batch-runs/${batchId}/rows?limit=1000`),
    ]);

    const batchPayload = await batchResponse.json();
    if (!batchResponse.ok) {
      throw new Error(batchPayload?.detail || batchPayload?.error || "Failed to load batch");
    }

    const rowsPayload = await rowsResponse.json();
    if (!rowsResponse.ok) {
      throw new Error(rowsPayload?.detail || rowsPayload?.error || "Failed to load batch rows");
    }

    setBatch(batchPayload as BatchResponse);
    setRows((rowsPayload?.rows || []) as BatchRow[]);
    setErrorDetail("");
  };

  useEffect(() => {
    void loadRecentBatches();
  }, []);

  useEffect(() => {
    if (!batch || !autoRefreshEnabled) return;
    if (isTerminalBatchStatus(batch.status)) return;

    const id = window.setInterval(() => {
      void (async () => {
        try {
          await fetchBatch(batch.batch_id);
        } catch {
          // Keep polling resilience; user can still press Refresh manually.
        }
      })();
    }, 5000);

    return () => window.clearInterval(id);
  }, [batch, autoRefreshEnabled]);

  const handleUpload = async () => {
    if (!file) {
      setMessage("Choose a CSV or XLSX file first.");
      return;
    }
    if (!targetMachineUuid) {
      setMessage("Pick a target worker before uploading.");
      return;
    }

    setBusy(true);
    setMessage("Uploading spreadsheet...");
    setErrorDetail("");
    try {
      const form = new FormData();
      form.append("spreadsheet", file);
      form.append("workflow_name", workflowName);
      form.append("target_machine_uuid", targetMachineUuid);
      form.append("column_mapping", mappingJson);

      const response = await fetch("/api/proxy/batch-runs/upload", {
        method: "POST",
        body: form,
      });
      const payload = (await response.json()) as UploadResponse | { detail?: string; error?: string };

      if (!response.ok) {
        const raw = await parseErrorBody(response);
        setErrorDetail(raw || JSON.stringify(payload));
        throw new Error((payload as { detail?: string; error?: string }).detail || (payload as { detail?: string; error?: string }).error || "Upload failed");
      }

      const uploadPayload = payload as UploadResponse;
      setBatch(uploadPayload.batch);
      setRows(uploadPayload.batch.rows || []);
      await loadRecentBatches();
      if (!uploadPayload.mapping_validation?.valid) {
        setMessage(
          `Uploaded with mapping issues. Missing: ${uploadPayload.mapping_validation.missing_required_fields.join(", ") || "none"}. Invalid: ${uploadPayload.mapping_validation.invalid_mapped_fields.join(", ") || "none"}.`,
        );
      } else {
        setMessage("Upload complete. Review rows and click Start Batch.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const handleStart = async () => {
    if (!batch) return;
    setBusy(true);
    setMessage("Starting batch run...");
    setErrorDetail("");
    try {
      const response = await fetch(`/api/proxy/batch-runs/${batch.batch_id}/start`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        const raw = await parseErrorBody(response);
        setErrorDetail(raw || JSON.stringify(payload));
        throw new Error(payload?.detail || payload?.error || "Failed to start batch");
      }
      await fetchBatch(batch.batch_id);
      await loadRecentBatches();
      setMessage(`Batch started. Queued rows: ${payload?.queued_rows ?? 0}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to start batch");
    } finally {
      setBusy(false);
    }
  };

  const handleRetryFailed = async () => {
    if (!batch) return;
    setBusy(true);
    setMessage("Retrying failed/needs-review rows...");
    setErrorDetail("");
    try {
      const response = await fetch(`/api/proxy/batch-runs/${batch.batch_id}/retry-failed`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        const raw = await parseErrorBody(response);
        setErrorDetail(raw || JSON.stringify(payload));
        throw new Error(payload?.detail || payload?.error || "Failed to retry rows");
      }
      await fetchBatch(batch.batch_id);
      await loadRecentBatches();
      setMessage(`Retry queued for ${payload?.retried_rows ?? 0} rows.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Retry failed");
    } finally {
      setBusy(false);
    }
  };

  const handleRetryNeedsReview = async () => {
    // Current backend retry endpoint includes needs_review rows.
    await handleRetryFailed();
  };

  const handleCancel = async () => {
    if (!batch) return;
    setBusy(true);
    setMessage("Canceling batch run...");
    setErrorDetail("");
    try {
      const response = await fetch(`/api/proxy/batch-runs/${batch.batch_id}/cancel`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        const raw = await parseErrorBody(response);
        setErrorDetail(raw || JSON.stringify(payload));
        throw new Error(payload?.detail || payload?.error || "Failed to cancel batch");
      }
      await fetchBatch(batch.batch_id);
      await loadRecentBatches();
      setMessage("Batch canceled.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Cancel failed");
    } finally {
      setBusy(false);
    }
  };

  const handleRefresh = async () => {
    setBusy(true);
    setErrorDetail("");
    try {
      await loadRecentBatches();
      if (batch?.batch_id) {
        await fetchBatch(batch.batch_id);
      }
      setMessage("Dashboard refreshed.");
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Refresh failed";
      setMessage(msg);
      setErrorDetail(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold text-slate-100">Spreadsheet Batch Workflow Runner</h3>
        <p className="text-xs text-slate-400">
          Upload CI Checks spreadsheets, map identity columns, run one child lookup task per row on a selected worker, and export results.
        </p>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h4 className="text-sm font-semibold text-slate-100">Recent Batches</h4>
          <button type="button" onClick={handleRefresh} disabled={busy} className={BTN_SECONDARY}>Refresh</button>
        </div>
        {recentBatches.length === 0 ? (
          <p className="text-xs text-slate-400">No batches yet.</p>
        ) : (
          <div className="grid gap-2">
            {recentBatches.slice(0, 10).map((item) => (
              <button
                key={item.batch_id}
                type="button"
                onClick={() => {
                  void fetchBatch(item.batch_id);
                }}
                className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-left text-xs text-slate-300 hover:border-cyan-400/60"
              >
                <span className="truncate">{item.workflow_name} - {item.batch_id.slice(0, 8)}</span>
                <span className={`rounded-full px-2 py-0.5 text-[11px] ${batchStatusBadgeClass(item.status)}`}>{item.status}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="grid gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-4 sm:grid-cols-2">
        <label className="text-xs text-slate-400">
          Workflow
          <input
            value={workflowName}
            onChange={(event) => setWorkflowName(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          />
        </label>

        <label className="text-xs text-slate-400">
          Target Worker
          <select
            value={targetMachineUuid}
            onChange={(event) => setTargetMachineUuid(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          >
            <option value="">Select worker</option>
            {workerOptions.map((machine) => (
              <option key={machine.machine_uuid} value={machine.machine_uuid}>
                {machine.machine_name || machine.machine_uuid} ({machine.status || "unknown"})
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-slate-400 sm:col-span-2">
          Spreadsheet (CSV or XLSX)
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
            className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 file:mr-3 file:rounded-md file:border-0 file:bg-cyan-500 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-slate-950"
          />
        </label>

        <label className="text-xs text-slate-400 sm:col-span-2">
          Column Mapping (JSON)
          <textarea
            value={mappingJson}
            onChange={(event) => setMappingJson(event.target.value)}
            rows={6}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          />
        </label>

        <div className="sm:col-span-2 flex flex-wrap gap-2">
          <button type="button" onClick={handleUpload} disabled={busy} className={BTN_PRIMARY}>
            {busy ? "Working..." : "Upload Batch"}
          </button>
          <button type="button" onClick={handleRefresh} disabled={busy} className={BTN_SECONDARY}>
            Refresh
          </button>
          <button type="button" onClick={handleStart} disabled={busy || !batch} className={BTN_SECONDARY}>
            Start Batch
          </button>
          <button type="button" onClick={handleRetryFailed} disabled={busy || !batch} className={BTN_SECONDARY}>
            Retry Failed Rows
          </button>
          <button
            type="button"
            onClick={handleRetryNeedsReview}
            disabled={busy || !batch}
            title="Retries rows currently marked needs_review"
            className={BTN_SECONDARY}
          >
            Retry Needs-Review Rows
          </button>
          <button type="button" onClick={handleCancel} disabled={busy || !batch} className={BTN_SECONDARY}>
            Cancel Batch
          </button>
          {batch ? (
            <a
              href={`/api/proxy/batch-runs/${batch.batch_id}/export`}
              className="inline-flex items-center rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-cyan-400/70 hover:text-cyan-100"
            >
              Export CSV
            </a>
          ) : null}
        </div>
      </div>

      {message ? <p className="text-sm text-slate-300">{message}</p> : null}
      {errorDetail ? (
        <details className="rounded-lg border border-rose-400/30 bg-rose-500/10 p-3 text-xs text-rose-100">
          <summary className="cursor-pointer font-semibold">Dashboard error details</summary>
          <pre className="mt-2 overflow-auto whitespace-pre-wrap">{errorDetail}</pre>
        </details>
      ) : null}

      {batch ? (
        <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/60 p-4">
          <div className="grid gap-3 rounded-xl border border-slate-800 bg-slate-900/60 p-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">Batch Summary</p>
              <p className="mt-1 text-sm text-slate-100">{batch.workflow_name}</p>
              <p className="text-xs text-slate-400">Batch ID: {batch.batch_id}</p>
              <p className="text-xs text-slate-400">Tenant: {batch.tenant_id || "-"}</p>
              <p className="text-xs text-slate-400">File: {batch.filename}</p>
              <p className="text-xs text-slate-400">Created by: {batch.created_by_name || "-"}</p>
            </div>

            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">Timing</p>
              <p className="text-xs text-slate-400">Created: {toDisplayTime(batch.created_at)}</p>
              <p className="text-xs text-slate-400">Started: {toDisplayTime(batch.started_at)}</p>
              <p className="text-xs text-slate-400">Completed: {toDisplayTime(batch.completed_at)}</p>
              <p className="text-xs text-slate-400">ETA: {formatEta(batch.summary?.estimated_remaining_seconds ?? null)}</p>
            </div>

            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">Worker & Status</p>
              <p className="text-xs text-slate-400">Worker: {batch.target_worker_name || "-"}</p>
              <p className="text-xs text-slate-400">Machine UUID: {batch.target_machine_uuid || "-"}</p>
              <span className={`mt-1 inline-block rounded-full px-2 py-1 text-xs ${batchStatusBadgeClass(batch.status)}`}>
                {batch.status}
              </span>
              <label className="mt-2 flex items-center gap-2 text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={autoRefreshEnabled}
                  onChange={(event) => setAutoRefreshEnabled(event.target.checked)}
                  className="h-4 w-4 rounded border-slate-700 bg-slate-900"
                />
                Auto-refresh every 5s while running
              </label>
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
            <div className="flex items-center justify-between text-xs text-slate-300">
              <span>Progress: {progressPercent}%</span>
              <span>
                Total: {batch.summary?.total_rows ?? 0} | Completed: {batch.summary?.completed_rows ?? 0} | Running: {batch.summary?.running_rows ?? 0} | Pending: {batch.summary?.pending_rows ?? 0}
              </span>
            </div>
            <div className="mt-2 h-3 w-full overflow-hidden rounded-full bg-slate-800">
              <div className="h-full bg-cyan-500 transition-all" style={{ width: `${progressPercent}%` }} />
            </div>
            <div className="mt-2 grid gap-2 text-xs text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
              <span>Failed: {batch.summary?.failed_rows ?? 0}</span>
              <span>Needs Review: {batch.summary?.needs_review_rows ?? 0}</span>
              <span>Skipped: {batch.summary?.skipped_rows ?? 0}</span>
              <span>Good (No Action): {batch.summary?.good_no_action_needed_rows ?? 0}</span>
              <span>Bad + Task Created: {batch.summary?.bad_payment_task_created_rows ?? 0}</span>
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            <label className="text-xs text-slate-400">
              Filter Rows
              <select
                value={rowFilter}
                onChange={(event) => setRowFilter(event.target.value as RowFilterOption)}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
              >
                <option value="all">all</option>
                <option value="pending">pending</option>
                <option value="running">running</option>
                <option value="completed">completed</option>
                <option value="good_no_action_needed">good_no_action_needed</option>
                <option value="bad_payment_task_created">bad_payment_task_created</option>
                <option value="needs_review">needs_review</option>
                <option value="failed">failed</option>
                <option value="skipped">skipped</option>
              </select>
            </label>
            <label className="text-xs text-slate-400 sm:col-span-2">
              Search (client, matched client, Keap ID, row #, error)
              <input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
              />
            </label>
          </div>

          <div className="max-h-[360px] overflow-auto rounded-lg border border-slate-800">
            <table className="min-w-full text-left text-xs text-slate-200">
              <thead className="bg-slate-900/90 text-slate-400">
                <tr>
                  <th className="px-3 py-2">Row #</th>
                  <th className="px-3 py-2">Client Name</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Matched Client</th>
                  <th className="px-3 py-2">Paid-through Date</th>
                  <th className="px-3 py-2">Decision</th>
                  <th className="px-3 py-2">Keap Task Created</th>
                  <th className="px-3 py-2">Keap Task ID</th>
                  <th className="px-3 py-2">Worker</th>
                  <th className="px-3 py-2">Error / Notes</th>
                  <th className="px-3 py-2">Completed At</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => (
                  <tr key={row.row_id} className="border-t border-slate-800">
                    <td className="px-3 py-2">{row.row_number}</td>
                    <td className="px-3 py-2">{row.mapped?.client_name || row.mapped?.member_name || [row.mapped?.first_name, row.mapped?.last_name].filter(Boolean).join(" ")}</td>
                    <td className="px-3 py-2">{row.status}</td>
                    <td className="px-3 py-2">{row.matched_client_name || "-"}</td>
                    <td className="px-3 py-2">{row.paid_through_date || row.mapped?.paid_through_date || "-"}</td>
                    <td className="px-3 py-2">{row.payment_status}</td>
                    <td className="px-3 py-2">{row.keap_task_created ? "yes" : "no"}</td>
                    <td className="px-3 py-2">{row.keap_task_id || "-"}</td>
                    <td className="px-3 py-2">{row.worker_name || row.assigned_machine_uuid || "-"}</td>
                    <td className="px-3 py-2 text-rose-300">{row.error || row.notes || ""}</td>
                    <td className="px-3 py-2">{toDisplayTime(row.completed_at)}</td>
                  </tr>
                ))}
                {filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="px-3 py-3 text-center text-slate-400">
                      No rows match current filters.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
