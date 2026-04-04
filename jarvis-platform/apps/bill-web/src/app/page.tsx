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
              <li key={machine.machine_uuid ?? `machine-${index}`}>
                {(machine.machine_name ?? "unknown")} | UUID: {(machine.machine_uuid ?? "-")} | Status: {(machine.status ?? "-")}
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
          <ul>
            {tasks.map((task, index) => (
              <li key={task.id ?? `task-${index}`}>
                {(task.id ?? "unknown-id")} | Status: {(task.status ?? "-")} | Type: {(task.payload?.task_type ?? "-")}
                {task.assigned_machine_uuid ? ` | Machine: ${task.assigned_machine_uuid}` : ""}
                {task.error ? ` | Error: ${task.error}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p>No tasks found.</p>
        )}
      </section>
    </main>
  );
}
