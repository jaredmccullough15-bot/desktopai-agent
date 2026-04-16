"use client";

import { useEffect, useState } from "react";

type TaskCreateResponse = {
  id?: string;
  status?: string;
  message?: string;
  [key: string]: unknown;
};

type HealthResponse = {
  status?: string;
};

type Machine = {
  machine_uuid?: string;
  machine_name?: string;
  status?: string;
  worker_version?: string;
  online?: boolean;
  last_seen?: string;
  execution_mode?: string;
  current_task_id?: string | null;
  current_step?: string | null;
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
  result_json?: {
    downloads?: Array<{
      filename?: string;
      local_path?: string;
      timestamp?: string;
    }>;
    [key: string]: unknown;
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

  if (configuredBase) {
    const normalized = configuredBase.replace(/\/$/, "");

    if (typeof window !== "undefined") {
      const currentHost = window.location.hostname;
      const localhostHosts = new Set(["localhost", "127.0.0.1", "0.0.0.0"]);

      try {
        const configuredUrl = new URL(normalized);
        if (!localhostHosts.has(currentHost) && localhostHosts.has(configuredUrl.hostname)) {
          configuredUrl.hostname = currentHost;
          return configuredUrl.toString().replace(/\/$/, "");
        }
      } catch {
        // Keep the configured value if it is not a valid absolute URL.
      }
    }

    return normalized;
  }

  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8000`;
  }

  return "";
};

export default function Home() {
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<TaskCreateResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [targetMachineUuid, setTargetMachineUuid] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [errors, setErrors] = useState<EndpointErrors>({});

  const selectedMachine = machines.find((machine) => machine.machine_uuid === targetMachineUuid) ?? null;

  const fetchJson = async <T,>(url: string): Promise<T> => {
    console.log(`[dashboard] Fetching URL: ${url}`);
    const response = await fetch(url, { cache: "no-store" });
    console.log(`[dashboard] Response status for ${url}: ${response.status}`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return (await response.json()) as T;
  };

  const loadDashboardData = async () => {
    setErrors({});

    const apiBase = getApiBase();

    if (!apiBase) {
      setErrors({
        config: "NEXT_PUBLIC_API_BASE is not set. Dashboard cannot reach bill-core."
      });
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
      setMachines(nextMachines);
      setTargetMachineUuid((current) => {
        if (!current) {
          return current;
        }

        const exists = nextMachines.some((machine) => machine.machine_uuid === current);
        return exists ? current : "";
      });
    } else {
      console.error(`[dashboard] Machines fetch failed for ${machinesUrl}`, machinesResult.reason);
      nextErrors.machines = `Machines fetch failed: ${String(machinesResult.reason)}`;
    }

    if (tasksResult.status === "fulfilled") {
      const nextTasks = Array.isArray(tasksResult.value) ? tasksResult.value : [];
      setTasks(nextTasks);
      if (nextTasks.length > 0) {
        setSelectedTask((current) => {
          if (!current?.id) {
            return nextTasks[0];
          }

          const match = nextTasks.find((task) => task.id === current.id);
          return match ?? nextTasks[0];
        });
      } else {
        setSelectedTask(null);
      }
    } else {
      console.error(`[dashboard] Tasks fetch failed for ${tasksUrl}`, tasksResult.reason);
      nextErrors.tasks = `Tasks fetch failed: ${String(tasksResult.reason)}`;
    }

    setErrors(nextErrors);
  };

  useEffect(() => {
    void loadDashboardData();
    const interval = setInterval(() => {
      void loadDashboardData();
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  const submitTask = async (body: Record<string, unknown>) => {
    setLoading(true);
    setActionError(null);
    try {
      const apiBase = getApiBase();

      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const taskCreateUrl = `${apiBase}/api/tasks`;
      const requestBody = targetMachineUuid
        ? { ...body, target_machine_uuid: targetMachineUuid }
        : body;
      console.log(`[dashboard] Fetching URL: ${taskCreateUrl}`);
      const res = await fetch(taskCreateUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody)
      });
      console.log(`[dashboard] Response status for ${taskCreateUrl}: ${res.status}`);
      const data = (await res.json()) as TaskCreateResponse;
      setResponse(data);
      if (!res.ok) {
        setActionError(`Request failed: ${res.status}`);
      } else {
        await loadDashboardData();
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const createTestTask = async () => {
    await submitTask({ payload: { source: "bill-web", type: "test" } });
  };

  const createScreenshotTask = async () => {
    await submitTask({
      task_type: "open_url_and_screenshot",
      url: "https://example.com",
      mode: "interactive_visible"
    });
  };

  const createVisibleWorkflowTask = async () => {
    await submitTask({
      task_type: "browser_workflow",
      mode: "interactive_visible",
      step_delay_ms: 900,
      steps: [
        { action: "open_url", url: "https://example.com" },
        { action: "wait_for_element", selector: "h1", timeout_ms: 15000 },
        { action: "take_screenshot", name: "visible-workflow" }
      ]
    });
  };

  const runSmartSherpaSync = async () => {
    setLoading(true);
    setActionError(null);
    try {
      const apiBase = getApiBase();

      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const procedureRunUrl = `${apiBase}/api/procedures/smart_sherpa_sync/run`;
      const requestBody: Record<string, unknown> = {
        mode: "interactive_visible",
        payload: {}
      };
      if (targetMachineUuid) {
        requestBody.target_machine_uuid = targetMachineUuid;
      }
      console.log(`[dashboard] Fetching URL: ${procedureRunUrl}`);
      const res = await fetch(procedureRunUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody)
      });
      console.log(`[dashboard] Response status for ${procedureRunUrl}: ${res.status}`);

      const data = (await res.json()) as TaskCreateResponse;
      setResponse(data);

      if (!res.ok) {
        setActionError(`Smart Sherpa Sync request failed: ${res.status}`);
      } else {
        await loadDashboardData();
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-white text-slate-900 p-8">
      <h1 className="text-3xl font-semibold mb-6">Bill Platform Dashboard</h1>
      <div className="mb-4 flex flex-col gap-2">
        <label htmlFor="target-machine" className="font-medium">Target Machine</label>
        <select
          id="target-machine"
          value={targetMachineUuid}
          onChange={(event) => setTargetMachineUuid(event.target.value)}
          className="max-w-3xl border rounded px-3 py-2 bg-white"
        >
          <option value="">Auto assign (first available worker)</option>
          {machines
            .map((machine) => {
              const machineUuid = machine.machine_uuid ?? "";
              const machineName = machine.machine_name ?? "unknown";
              if (!machineUuid) {
                return null;
              }

              return (
                <option key={machineUuid} value={machineUuid}>
                  {machineName} ({machineUuid}){typeof machine.online === "boolean" ? ` | online=${machine.online}` : ""}
                </option>
              );
            })}
        </select>
        <p className="text-sm text-slate-600">
          {selectedMachine
            ? `Selected: ${selectedMachine.machine_name ?? "unknown"} (${selectedMachine.machine_uuid ?? "-"})`
            : "Selected: Auto assign"}
        </p>
      </div>
      <div className="flex gap-3">
        <button
          type="button"
          onClick={createTestTask}
          disabled={loading}
          className="px-4 py-2 rounded bg-slate-900 text-white disabled:opacity-50"
        >
          {loading ? "Creating..." : "Create Test Task"}
        </button>
        <button
          type="button"
          onClick={createScreenshotTask}
          disabled={loading}
          className="px-4 py-2 rounded bg-slate-700 text-white disabled:opacity-50"
        >
          {loading ? "Creating..." : "Create Screenshot Task"}
        </button>
        <button
          type="button"
          onClick={createVisibleWorkflowTask}
          disabled={loading}
          className="px-4 py-2 rounded bg-indigo-700 text-white disabled:opacity-50"
        >
          {loading ? "Creating..." : "Create Visible Workflow Task"}
        </button>
        <button
          type="button"
          onClick={runSmartSherpaSync}
          disabled={loading}
          className="px-4 py-2 rounded bg-emerald-700 text-white disabled:opacity-50"
        >
          {loading ? "Creating..." : "Run Smart Sherpa Sync"}
        </button>
      </div>

      {actionError && <p className="mt-4 text-red-600">{actionError}</p>}

      {response && (
        <pre className="mt-4 p-4 rounded bg-slate-100 overflow-auto text-sm">
          {JSON.stringify(response, null, 2)}
        </pre>
      )}

      {errors.config && <p className="mt-4 text-red-600">{errors.config}</p>}

      <section className="mt-8">
        <h2 className="text-xl font-semibold mb-3">System Health</h2>
        {errors.health ? (
          <p className="text-red-600">{errors.health}</p>
        ) : health ? (
          <p>Status: {health.status ?? "unknown"}</p>
        ) : (
          <p>No health data.</p>
        )}
      </section>

      <section className="mt-8">
        <h2 className="text-xl font-semibold mb-3">Machines</h2>
        {errors.machines ? (
          <p className="text-red-600">{errors.machines}</p>
        ) : machines.length > 0 ? (
          <ul className="list-disc pl-5 space-y-1">
            {machines.map((machine, index) => (
              <li key={machine.machine_uuid ?? `machine-${index}`}>
                {(machine.machine_name ?? "unknown")} | UUID: {(machine.machine_uuid ?? "-")} | Status: {(machine.status ?? "-")}
                {typeof machine.online === "boolean" ? ` | Online: ${machine.online}` : ""}
                {machine.worker_version ? ` | Version: ${machine.worker_version}` : ""}
                {machine.execution_mode ? ` | Mode: ${machine.execution_mode}` : ""}
                {machine.current_task_id ? ` | Current Task: ${machine.current_task_id}` : ""}
                {machine.current_step ? ` | Current Step: ${machine.current_step}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p>No machines found.</p>
        )}
      </section>

      <section className="mt-8">
        <h2 className="text-xl font-semibold mb-3">Recent Tasks</h2>
        {errors.tasks ? (
          <p className="text-red-600">{errors.tasks}</p>
        ) : tasks.length > 0 ? (
          <ul className="space-y-2">
            {tasks.map((task, index) => (
              <li key={task.id ?? `task-${index}`}>
                <button
                  type="button"
                  onClick={() => setSelectedTask(task)}
                  className="w-full text-left border rounded p-2 hover:bg-slate-50"
                >
                  {(task.id ?? "unknown-id")} | Status: {(task.status ?? "-")} | Type: {(task.payload?.task_type ?? "-")}
                  {task.assigned_machine_uuid ? ` | Machine: ${task.assigned_machine_uuid}` : ""}
                  {task.error ? ` | Error: ${task.error}` : ""}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p>No tasks found.</p>
        )}
      </section>

      <section className="mt-8">
        <h2 className="text-xl font-semibold mb-3">Task Result Panel</h2>
        {selectedTask ? (
          <div className="border rounded p-3 bg-slate-50">
            <p><strong>Task ID:</strong> {selectedTask.id ?? "-"}</p>
            <p><strong>Status:</strong> {selectedTask.status ?? "-"}</p>
            <p><strong>Type:</strong> {selectedTask.payload?.task_type ?? "-"}</p>

            <div className="mt-3">
              <p className="font-semibold">Downloaded Files</p>
              {(selectedTask.result_json?.downloads ?? []).length > 0 ? (
                <ul className="list-disc pl-5 space-y-1 mt-1">
                  {(selectedTask.result_json?.downloads ?? []).map((download, index) => (
                    <li key={`${selectedTask.id ?? "task"}-download-${index}`}>
                      Filename: {download.filename ?? "-"} | Path: {download.local_path ?? "-"}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1">No downloads recorded for this task.</p>
              )}
            </div>

            <div className="mt-3">
              <p className="font-semibold">Result JSON</p>
              <pre className="mt-1 p-2 rounded bg-white overflow-auto text-sm border">
                {JSON.stringify(selectedTask.result_json ?? {}, null, 2)}
              </pre>
            </div>
          </div>
        ) : (
          <p>No task selected.</p>
        )}
      </section>
    </main>
  );
}
