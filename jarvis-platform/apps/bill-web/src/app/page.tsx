"use client";

import { useEffect, useState } from "react";

type HealthResponse = {
  status?: string;
};

type Machine = {
  machine_uuid?: string;
  machine_name?: string;
  worker_name?: string;
  status?: string;
  worker_version?: string;
  online?: boolean;
  last_seen?: string;
};

type Task = {
  id?: string;
  status?: string;
  payload?: {
    task_type?: string;
    [key: string]: unknown;
  };
  assigned_machine_uuid?: string | null;
  error?: string | null;
  created_at?: string;
};

type HumanExplanation = {
  what_happened: string;
  likely_cause: string;
  meaning: string;
  recommended_next_action: string;
  category: string;
  memory_hint?: string;
};

type TaskExplain = {
  task_id: string;
  human_summary: string;
  explanation: HumanExplanation | null;
  technical: {
    error?: string;
    status?: string;
    failure_classification?: string;
    likely_root_cause?: string;
    supporting_evidence?: string;
    reflection_id?: string;
    confidence?: number;
  };
};

type EndpointErrors = {
  health?: string;
  machines?: string;
  tasks?: string;
  config?: string;
};

const getApiBase = (): string => {
  const configuredBase = process.env.NEXT_PUBLIC_API_BASE?.trim();

  const deriveApiBaseFromHost = (): string => {
    if (typeof window === "undefined") {
      return "";
    }

    const { protocol, hostname } = window.location;
    const localhostHosts = new Set(["localhost", "127.0.0.1", "0.0.0.0"]);

    if (localhostHosts.has(hostname)) {
      return `${protocol}//${hostname}:8000`;
    }

    if (hostname.startsWith("core.")) {
      return `${protocol}//api.${hostname.slice("core.".length)}`;
    }

    return `${protocol}//api.${hostname}`;
  };

  if (configuredBase) {
    const normalized = configuredBase.replace(/\/$/, "");

    if (typeof window !== "undefined") {
      const currentHost = window.location.hostname;
      const localhostHosts = new Set(["localhost", "127.0.0.1", "0.0.0.0"]);

      try {
        const configuredUrl = new URL(normalized);
        if (!localhostHosts.has(currentHost) && localhostHosts.has(configuredUrl.hostname)) {
          configuredUrl.hostname = currentHost.startsWith("core.")
            ? `api.${currentHost.slice("core.".length)}`
            : `api.${currentHost}`;
          configuredUrl.port = "";
          return configuredUrl.toString().replace(/\/$/, "");
        }
      } catch {
        // Keep configured value if it is not a valid absolute URL.
      }
    }

    return normalized;
  }

  return deriveApiBaseFromHost();
};

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [errors, setErrors] = useState<EndpointErrors>({});
  const [loading, setLoading] = useState(true);
  const [explanations, setExplanations] = useState<Record<string, TaskExplain>>({});
  const [expandedTechnical, setExpandedTechnical] = useState<Set<string>>(new Set());

  const fetchJson = async <T,>(url: string): Promise<T> => {
    console.log(`[dashboard] Fetching URL: ${url}`);
    const response = await fetch(url, { cache: "no-store" });
    console.log(`[dashboard] Response status for ${url}: ${response.status}`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return (await response.json()) as T;
  };

  useEffect(() => {
    const loadDashboardData = async () => {
      setLoading(true);
      setErrors({});

      const apiBase = getApiBase();

      if (!apiBase) {
        setErrors({
          config: "NEXT_PUBLIC_API_BASE is not set. Dashboard cannot reach bill-core."
        });
        setLoading(false);
        return;
      }

      const healthUrl = `${apiBase}/health`;
      const machinesUrl = `${apiBase}/api/machines`;
      const tasksUrl = `${apiBase}/api/tasks`;

      const [healthResult, machinesResult, tasksResult] = await Promise.allSettled([
        fetchJson<HealthResponse>(healthUrl),
        fetchJson<Machine[]>(machinesUrl),
        fetchJson<Task[]>(tasksUrl)
      ]);

      const nextErrors: EndpointErrors = {};

      if (healthResult.status === "fulfilled") {
        setHealth(healthResult.value);
      } else {
        console.error(`[dashboard] Health fetch failed for ${healthUrl}`, healthResult.reason);
        nextErrors.health = `Health fetch failed: ${String(healthResult.reason)}`;
      }

      if (machinesResult.status === "fulfilled") {
        const nextMachines = Array.isArray(machinesResult.value) ? machinesResult.value : [];
        console.log("[dashboard] /api/machines raw response", machinesResult.value);
        console.table(
          nextMachines.map((machine) => ({
            machine_uuid: machine.machine_uuid ?? null,
            worker_name: machine.worker_name ?? machine.machine_name ?? null,
            status: machine.status ?? null,
          }))
        );
        setMachines(nextMachines);
      } else {
        console.error(`[dashboard] Machines fetch failed for ${machinesUrl}`, machinesResult.reason);
        nextErrors.machines = `Machines fetch failed: ${String(machinesResult.reason)}`;
      }

      if (tasksResult.status === "fulfilled") {
        setTasks(Array.isArray(tasksResult.value) ? tasksResult.value : []);
      } else {
        console.error(`[dashboard] Tasks fetch failed for ${tasksUrl}`, tasksResult.reason);
        nextErrors.tasks = `Tasks fetch failed: ${String(tasksResult.reason)}`;
      }

      setErrors(nextErrors);
      setLoading(false);

      // Fetch human-readable explanations for failed tasks in background
      if (tasksResult.status === "fulfilled") {
        const allTasks = Array.isArray(tasksResult.value) ? tasksResult.value : [];
        const failedTasks = allTasks.filter(t => t.status === "failed" || t.status === "error");
        if (failedTasks.length > 0) {
          const explainResults = await Promise.allSettled(
            failedTasks.map(t =>
              t.id
                ? fetchJson<TaskExplain>(`${apiBase}/api/tasks/${t.id}/explain`)
                : Promise.reject(new Error("no id"))
            )
          );
          const nextExplanations: Record<string, TaskExplain> = {};
          explainResults.forEach((result, i) => {
            const taskId = failedTasks[i]?.id;
            if (result.status === "fulfilled" && taskId) {
              nextExplanations[taskId] = result.value;
            }
          });
          setExplanations(nextExplanations);
        }
      }
    };

    void loadDashboardData();
  }, []);

  return (
    <main style={{ padding: "20px", fontFamily: "Arial, sans-serif" }}>
      <h1>Bill Platform Dashboard</h1>

      {loading && <p>Loading dashboard data...</p>}

      {errors.config && <p style={{ color: "red" }}>{errors.config}</p>}

      <section style={{ marginTop: "16px" }}>
        <h2>System Health</h2>
        {errors.health ? (
          <p style={{ color: "red" }}>{errors.health}</p>
        ) : health ? (
          <p>Status: {health.status ?? "unknown"}</p>
        ) : (
          <p>No health data.</p>
        )}
      </section>

      <section style={{ marginTop: "16px" }}>
        <h2>Machines</h2>
        {errors.machines ? (
          <p style={{ color: "red" }}>{errors.machines}</p>
        ) : machines.length > 0 ? (
          <ul>
            {machines.map((machine, index) => (
              <li key={machine.machine_uuid ?? `machine-${index}`} style={{ marginBottom: "8px" }}>
                <span style={{ fontWeight: 600 }}>{machine.machine_name ?? "unknown"}</span>
                {" | UUID: "}{machine.machine_uuid ?? "-"}
                {" | Status: "}
                <span style={{ fontWeight: 600, color: machine.status === "error" ? "#dc2626" : machine.status === "idle" ? "#16a34a" : machine.status === "busy" ? "#d97706" : "#374151" }}>
                  {machine.status ?? "-"}
                </span>
                {machine.status === "error" && (
                  <span style={{ marginLeft: "8px", background: "#fef2f2", border: "1px solid #fecaca", padding: "2px 8px", borderRadius: "4px", fontSize: "12px", color: "#7f1d1d" }}>
                    Browser connection lost — restart this worker to recover
                  </span>
                )}
                {typeof machine.online === "boolean" ? ` | Online: ${machine.online}` : ""}
                {machine.worker_version ? ` | Version: ${machine.worker_version}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p>No machines found.</p>
        )}

        <div style={{ marginTop: "12px", border: "1px solid #f59e0b", background: "#fffbeb", padding: "10px", fontSize: "12px" }}>
          <p style={{ fontWeight: 700, marginBottom: "6px" }}>Temporary machine debug</p>
          <pre style={{ overflow: "auto", margin: 0 }}>
            {JSON.stringify(
              machines.map((machine) => ({
                machine_uuid: machine.machine_uuid ?? null,
                worker_name: machine.worker_name ?? machine.machine_name ?? null,
                status: machine.status ?? null,
              })),
              null,
              2
            )}
          </pre>
        </div>
      </section>

      <section style={{ marginTop: "16px" }}>
        <h2>Recent Tasks</h2>
        {errors.tasks ? (
          <p style={{ color: "red" }}>{errors.tasks}</p>
        ) : tasks.length > 0 ? (
          <ul style={{ paddingLeft: 0 }}>
            {tasks.map((task, index) => {
              const taskId = task.id ?? `task-${index}`;
              const explain = task.id ? explanations[task.id] : undefined;
              const isExpanded = expandedTechnical.has(taskId);
              const isFailed = task.status === "failed" || task.status === "error";

              return (
                <li
                  key={taskId}
                  style={{
                    marginBottom: "10px",
                    listStyle: "none",
                    border: `1px solid ${isFailed ? "#fecaca" : "#e5e7eb"}`,
                    padding: "10px 12px",
                    borderRadius: "6px",
                    background: isFailed ? "#fff7f7" : "#ffffff",
                  }}
                >
                  {/* Header row */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ fontSize: "13px" }}>
                      <span style={{ fontWeight: 600 }}>{task.payload?.task_type ?? "Task"}</span>
                      <span style={{ color: "#9ca3af", marginLeft: "6px", fontSize: "11px" }}>{task.id ?? ""}</span>
                    </div>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: "12px",
                        fontSize: "11px",
                        fontWeight: 600,
                        background:
                          task.status === "completed" ? "#d1fae5" :
                          isFailed ? "#fee2e2" :
                          task.status === "running" ? "#dbeafe" : "#f3f4f6",
                        color:
                          task.status === "completed" ? "#065f46" :
                          isFailed ? "#991b1b" :
                          task.status === "running" ? "#1e40af" : "#374151",
                      }}
                    >
                      {task.status ?? "-"}
                    </span>
                  </div>

                  {/* Human summary */}
                  {explain?.human_summary && (
                    <p style={{ margin: "6px 0 0", fontSize: "13px", color: "#374151", fontWeight: 500 }}>
                      {explain.human_summary}
                    </p>
                  )}

                  {/* Explanation detail */}
                  {explain?.explanation && (
                    <div style={{ marginTop: "8px", fontSize: "12px", color: "#4b5563", background: "#f9fafb", padding: "8px 10px", borderRadius: "4px", lineHeight: 1.5 }}>
                      <p style={{ margin: "0 0 4px" }}><strong>What happened:</strong> {explain.explanation.what_happened}</p>
                      <p style={{ margin: "0 0 4px" }}><strong>Likely cause:</strong> {explain.explanation.likely_cause}</p>
                      <p style={{ margin: "0" }}><strong>Next step:</strong> {explain.explanation.recommended_next_action}</p>
                      {explain.explanation.memory_hint && (
                        <p style={{ margin: "6px 0 0", color: "#7c3aed", fontStyle: "italic", fontSize: "11px" }}>
                          {explain.explanation.memory_hint}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Fallback raw error if no explain available yet */}
                  {!explain && isFailed && task.error && (
                    <p style={{ margin: "6px 0 0", fontSize: "12px", color: "#dc2626", fontFamily: "monospace" }}>
                      {task.error}
                    </p>
                  )}

                  {/* Expand/collapse technical details */}
                  {(explain ?? (isFailed && task.error)) && (
                    <button
                      onClick={() =>
                        setExpandedTechnical(prev => {
                          const next = new Set(prev);
                          if (next.has(taskId)) next.delete(taskId); else next.add(taskId);
                          return next;
                        })
                      }
                      style={{ marginTop: "6px", fontSize: "11px", color: "#6b7280", background: "none", border: "none", cursor: "pointer", padding: 0, textDecoration: "underline" }}
                    >
                      {isExpanded ? "▾ Hide technical details" : "▸ Show technical details"}
                    </button>
                  )}

                  {isExpanded && (
                    <div style={{ marginTop: "6px", fontSize: "11px", color: "#374151", background: "#f3f4f6", padding: "8px", borderRadius: "4px", fontFamily: "monospace", lineHeight: 1.6 }}>
                      {explain?.technical?.failure_classification && <div>Classification: {explain.technical.failure_classification}</div>}
                      {explain?.technical?.likely_root_cause && <div>Root cause: {explain.technical.likely_root_cause}</div>}
                      {explain?.technical?.supporting_evidence && <div>Evidence: {explain.technical.supporting_evidence}</div>}
                      {typeof explain?.technical?.confidence === "number" && (
                        <div>Confidence: {Math.round(explain.technical.confidence * 100)}%</div>
                      )}
                      {(explain?.technical?.error ?? task.error) && (
                        <div style={{ marginTop: "4px", wordBreak: "break-all" }}>Raw error: {explain?.technical?.error ?? task.error}</div>
                      )}
                    </div>
                  )}

                  {/* Footer metadata */}
                  <div style={{ marginTop: "6px", fontSize: "11px", color: "#9ca3af" }}>
                    {task.assigned_machine_uuid && <span>Machine: {task.assigned_machine_uuid}</span>}
                    {task.created_at && <span style={{ marginLeft: task.assigned_machine_uuid ? "6px" : 0 }}>{task.created_at}</span>}
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <p>No tasks found.</p>
        )}
      </section>
    </main>
  );
}
