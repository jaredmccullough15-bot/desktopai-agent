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
  worker_name?: string;
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
  workflows?: string;
  audit?: string;
  config?: string;
};

type BrainTaskRef = {
  id?: string;
  status?: string;
};

type BrainCommandResponse = {
  recognized_intent?: string;
  command?: string;
  before_execution?: string;
  after_execution?: string;
  selected_workflow?: string | null;
  selected_worker_uuid?: string | null;
  selected_worker_name?: string | null;
  suggested_next_action?: string | null;
  retry_recommended?: boolean;
  task?: BrainTaskRef | null;
};

type ChatEntry = {
  role: "user" | "assistant";
  message: string;
};

type WorkflowRecord = {
  workflow_name: string;
  description: string;
  required_inputs: string[];
  login_or_session_required: boolean;
  safe_for_unattended: boolean;
  compatible_worker_types: string[];
  procedure_name?: string | null;
};

type BrainAuditEntry = {
  timestamp?: string;
  original_user_text?: string;
  interpreted_intent?: string;
  selected_workflow?: string | null;
  selected_worker?: string | null;
  queued_task_id?: string | null;
  before_execution?: string;
  after_execution?: string;
};

type ActionFeedback = {
  kind: "success" | "error";
  message: string;
  timestamp: string;
};

const getApiBase = (): string => {
  const configuredBase = process.env.NEXT_PUBLIC_API_BASE?.trim();

  const deriveApiBaseFromHost = (): string => {
    if (typeof window === "undefined") {
      return "";
    }

    const { protocol, hostname, port } = window.location;
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
        // Keep the configured value if it is not a valid absolute URL.
      }
    }

    return normalized;
  }

  return deriveApiBaseFromHost();
};

export default function Home() {
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<TaskCreateResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [taskActionFeedback, setTaskActionFeedback] = useState<ActionFeedback | null>(null);
  const [taskActionBusyKey, setTaskActionBusyKey] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [targetMachineUuid, setTargetMachineUuid] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [errors, setErrors] = useState<EndpointErrors>({});
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [workflows, setWorkflows] = useState<WorkflowRecord[]>([]);
  const [auditEntries, setAuditEntries] = useState<BrainAuditEntry[]>([]);
  const [helperWorkflow, setHelperWorkflow] = useState("");
  const [helperWorkerUuid, setHelperWorkerUuid] = useState("");
  const [helperClientName, setHelperClientName] = useState("");
  const [helperHouseholdName, setHelperHouseholdName] = useState("");
  const [helperMaxClients, setHelperMaxClients] = useState("");
  const [helperMaxPages, setHelperMaxPages] = useState("");
  const [helperRetryFailedOnly, setHelperRetryFailedOnly] = useState(false);
  const [helperFreeText, setHelperFreeText] = useState("");
  const [helperBusy, setHelperBusy] = useState(false);
  const [helperFeedback, setHelperFeedback] = useState<ActionFeedback | null>(null);
  const [chatHistory, setChatHistory] = useState<ChatEntry[]>([
    {
      role: "assistant",
      message:
        "I am Bill Core Orchestrator. Ask things like: 'Which worker is free?', 'What failed last?', or 'Run Marketplace workflow on Worker A'.",
    },
  ]);

  const selectedMachine = machines.find((machine) => machine.machine_uuid === targetMachineUuid) ?? null;

  const activeTaskStatuses = new Set(["queued", "assigned", "running"]);

  const setFeedback = (
    setter: (feedback: ActionFeedback | null) => void,
    kind: "success" | "error",
    message: string,
  ) => {
    setter({
      kind,
      message,
      timestamp: new Date().toLocaleTimeString(),
    });
  };

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
      console.log("[dashboard] /api/machines raw response", machinesResult.value);
      console.table(
        nextMachines.map((machine) => ({
          machine_uuid: machine.machine_uuid ?? null,
          worker_name: machine.worker_name ?? machine.machine_name ?? null,
          status: machine.status ?? null,
        }))
      );
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

  const loadBrainPanels = async () => {
    const apiBase = getApiBase();
    if (!apiBase) {
      return;
    }

    const workflowsUrl = `${apiBase}/api/workflows`;
    const auditUrl = `${apiBase}/api/brain/audit?limit=20`;
    const [workflowsResult, auditResult] = await Promise.allSettled([
      fetchJson<WorkflowRecord[]>(workflowsUrl),
      fetchJson<BrainAuditEntry[]>(auditUrl),
    ]);

    setErrors((current) => {
      const next = { ...current };

      if (workflowsResult.status === "fulfilled") {
        const nextWorkflows = Array.isArray(workflowsResult.value) ? workflowsResult.value : [];
        setWorkflows(nextWorkflows);
        if (!helperWorkflow && nextWorkflows.length > 0) {
          setHelperWorkflow(nextWorkflows[0].workflow_name);
        }
        delete next.workflows;
      } else {
        next.workflows = `Workflows fetch failed: ${String(workflowsResult.reason)}`;
      }

      if (auditResult.status === "fulfilled") {
        setAuditEntries(Array.isArray(auditResult.value) ? auditResult.value.slice().reverse() : []);
        delete next.audit;
      } else {
        next.audit = `Audit fetch failed: ${String(auditResult.reason)}`;
      }

      return next;
    });
  };

  useEffect(() => {
    void loadDashboardData();
    const interval = setInterval(() => {
      void loadDashboardData();
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    void loadBrainPanels();
    const interval = setInterval(() => {
      void loadBrainPanels();
    }, 7000);

    return () => clearInterval(interval);
  }, [helperWorkflow]);

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

  const submitBrainCommand = async (
    commandOverride?: string,
    workerOverrideUuid?: string,
  ) => {
    const command = (commandOverride ?? chatInput).trim();
    if (!command || chatLoading) {
      return;
    }

    setChatLoading(true);
    setChatHistory((current) => [...current, { role: "user", message: command }]);
    if (!commandOverride) {
      setChatInput("");
    }

    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const url = `${apiBase}/api/brain/command`;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command,
          target_machine_uuid: workerOverrideUuid || targetMachineUuid || undefined,
        }),
      });

      const body = (await response.json()) as BrainCommandResponse;
      if (!response.ok) {
        throw new Error(`Brain command failed: ${response.status}`);
      }

      const lines: string[] = [];
      if (body.before_execution) {
        lines.push(`Before: ${body.before_execution}`);
      }
      if (body.after_execution) {
        lines.push(`After: ${body.after_execution}`);
      }
      if (body.selected_workflow) {
        lines.push(`Workflow: ${body.selected_workflow}`);
      }
      if (body.selected_worker_name || body.selected_worker_uuid) {
        lines.push(
          `Worker: ${body.selected_worker_name ?? "unknown"} (${body.selected_worker_uuid ?? "no uuid"})`
        );
      }
      if (body.task?.id) {
        lines.push(`Task queued: ${body.task.id}`);
      }
      if (body.suggested_next_action) {
        lines.push(`Next: ${body.suggested_next_action}`);
      }

      setChatHistory((current) => [
        ...current,
        {
          role: "assistant",
          message: lines.join("\n"),
        },
      ]);

      await loadDashboardData();
      await loadBrainPanels();
    } catch (error) {
      setChatHistory((current) => [
        ...current,
        {
          role: "assistant",
          message: `I hit an error while processing that command: ${
            error instanceof Error ? error.message : "Unknown error"
          }`,
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const cancelTask = async (taskId?: string) => {
    if (!taskId) {
      setFeedback(setTaskActionFeedback, "error", "Cancel failed: task id is missing.");
      return;
    }

    setTaskActionBusyKey(`cancel-${taskId}`);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const url = `${apiBase}/api/tasks/${taskId}/cancel`;
      const res = await fetch(url, { method: "POST" });
      const body = (await res.json()) as { message?: string; detail?: string };

      if (!res.ok) {
        throw new Error(body.detail ?? `Cancel failed (${res.status})`);
      }

      setFeedback(
        setTaskActionFeedback,
        "success",
        body.message ?? `Task ${taskId} canceled successfully.`,
      );
      await loadDashboardData();
      await loadBrainPanels();
    } catch (error) {
      setFeedback(
        setTaskActionFeedback,
        "error",
        `Cancel failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setTaskActionBusyKey(null);
    }
  };

  const retryFailedTask = async (task: Task) => {
    if (!task.id) {
      setFeedback(setTaskActionFeedback, "error", "Retry failed: task id is missing.");
      return;
    }

    const status = (task.status ?? "").toLowerCase();
    if (status !== "failed") {
      setFeedback(setTaskActionFeedback, "error", `Task ${task.id} is not failed.`);
      return;
    }

    setTaskActionBusyKey(`retry-${task.id}`);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const retryPayload: Record<string, unknown> = {
        ...(task.payload ?? {}),
        retry_of_task_id: task.id,
      };

      if (!retryPayload.target_machine_uuid && task.assigned_machine_uuid) {
        retryPayload.target_machine_uuid = task.assigned_machine_uuid;
      }

      const url = `${apiBase}/api/tasks`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload: retryPayload }),
      });
      const body = (await res.json()) as TaskCreateResponse;
      if (!res.ok) {
        throw new Error(body.message ?? `Retry failed (${res.status})`);
      }

      setFeedback(
        setTaskActionFeedback,
        "success",
        `Retry queued. Original: ${task.id}. New task: ${body.id ?? "unknown"}.`,
      );
      await loadDashboardData();
      await loadBrainPanels();
    } catch (error) {
      setFeedback(
        setTaskActionFeedback,
        "error",
        `Retry failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setTaskActionBusyKey(null);
    }
  };

  const runGuidedCommand = async () => {
    if (!helperWorkflow || helperBusy) {
      return;
    }

    setHelperBusy(true);
    try {
      const fragments: string[] = [];

      if (helperWorkflow === "smart_sherpa_sync") {
        fragments.push("run smart sherpa sync");
      } else if (helperWorkflow === "marketplace_workflow") {
        fragments.push("run marketplace workflow");
      } else {
        fragments.push(`run workflow ${helperWorkflow}`);
      }

      if (helperClientName.trim()) {
        fragments.push(`for client ${helperClientName.trim()}`);
      }
      if (helperHouseholdName.trim()) {
        fragments.push(`for household ${helperHouseholdName.trim()}`);
      }
      if (helperMaxClients.trim()) {
        fragments.push(`max clients ${helperMaxClients.trim()}`);
      }
      if (helperMaxPages.trim()) {
        fragments.push(`max pages ${helperMaxPages.trim()}`);
      }
      if (helperRetryFailedOnly) {
        fragments.push("retry failed only");
      }

      const command = fragments.join(" ");
      await submitBrainCommand(command, helperWorkerUuid || undefined);

      setFeedback(
        setHelperFeedback,
        "success",
        `Guided command submitted: ${command}`,
      );
    } catch (error) {
      setFeedback(
        setHelperFeedback,
        "error",
        `Guided command failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setHelperBusy(false);
    }
  };

  const runFreeTextCommand = async () => {
    const command = helperFreeText.trim();
    if (!command || helperBusy) {
      return;
    }

    setHelperBusy(true);
    try {
      await submitBrainCommand(command, helperWorkerUuid || undefined);
      setFeedback(setHelperFeedback, "success", "Free-text command submitted.");
      setHelperFreeText("");
    } catch (error) {
      setFeedback(
        setHelperFeedback,
        "error",
        `Free-text command failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setHelperBusy(false);
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

        <div className="mt-4 rounded border border-amber-300 bg-amber-50 p-3 text-xs">
          <p className="font-semibold text-amber-900">Temporary machine debug</p>
          <pre className="mt-2 overflow-auto text-amber-950">
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

      <section className="mt-8">
        <h2 className="text-xl font-semibold mb-3">Recent Tasks</h2>
        {taskActionFeedback && (
          <p
            className={
              taskActionFeedback.kind === "success"
                ? "mb-3 rounded border border-emerald-300 bg-emerald-50 p-2 text-emerald-800"
                : "mb-3 rounded border border-red-300 bg-red-50 p-2 text-red-700"
            }
          >
            {taskActionFeedback.message} ({taskActionFeedback.timestamp})
          </p>
        )}
        {errors.tasks ? (
          <p className="text-red-600">{errors.tasks}</p>
        ) : tasks.length > 0 ? (
          <ul className="space-y-2">
            {tasks.map((task, index) => (
              <li key={task.id ?? `task-${index}`}>
                <div className="border rounded p-2">
                  <button
                    type="button"
                    onClick={() => setSelectedTask(task)}
                    className="w-full text-left hover:bg-slate-50"
                  >
                    {(task.id ?? "unknown-id")} | Status: {(task.status ?? "-")} | Type: {(task.payload?.task_type ?? "-")}
                    {task.assigned_machine_uuid ? ` | Machine: ${task.assigned_machine_uuid}` : ""}
                    {task.error ? ` | Error: ${task.error}` : ""}
                  </button>

                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={!task.id || !activeTaskStatuses.has((task.status ?? "").toLowerCase()) || taskActionBusyKey !== null}
                      onClick={() => void cancelTask(task.id)}
                      className="rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-900 disabled:opacity-50"
                    >
                      {taskActionBusyKey === `cancel-${task.id}` ? "Canceling..." : "Cancel active task"}
                    </button>
                    <button
                      type="button"
                      disabled={!task.id || (task.status ?? "").toLowerCase() !== "failed" || taskActionBusyKey !== null}
                      onClick={() => void retryFailedTask(task)}
                      className="rounded border border-blue-300 bg-blue-50 px-2 py-1 text-xs text-blue-900 disabled:opacity-50"
                    >
                      {taskActionBusyKey === `retry-${task.id}` ? "Retrying..." : "Retry failed task"}
                    </button>
                  </div>
                </div>
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

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!selectedTask.id || !activeTaskStatuses.has((selectedTask.status ?? "").toLowerCase()) || taskActionBusyKey !== null}
                onClick={() => void cancelTask(selectedTask.id)}
                className="rounded border border-amber-300 bg-amber-50 px-3 py-1 text-sm text-amber-900 disabled:opacity-50"
              >
                {taskActionBusyKey === `cancel-${selectedTask.id}` ? "Canceling..." : "Cancel active task"}
              </button>
              <button
                type="button"
                disabled={!selectedTask.id || (selectedTask.status ?? "").toLowerCase() !== "failed" || taskActionBusyKey !== null}
                onClick={() => void retryFailedTask(selectedTask)}
                className="rounded border border-blue-300 bg-blue-50 px-3 py-1 text-sm text-blue-900 disabled:opacity-50"
              >
                {taskActionBusyKey === `retry-${selectedTask.id}` ? "Retrying..." : "Retry failed task"}
              </button>
            </div>

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

      <section className="mt-8 border rounded p-4 bg-slate-50">
        <h2 className="text-xl font-semibold mb-3">Command Helper</h2>
        <p className="text-sm text-slate-600 mb-3">
          Guided workflow command builder with parameter inputs and optional free-text fallback.
        </p>

        {errors.workflows && <p className="mb-2 text-red-600">{errors.workflows}</p>}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="text-sm">
            <span className="mb-1 block font-medium">Workflow</span>
            <select
              value={helperWorkflow}
              onChange={(event) => setHelperWorkflow(event.target.value)}
              className="w-full border rounded px-3 py-2 bg-white"
            >
              {workflows.map((workflow) => (
                <option key={workflow.workflow_name} value={workflow.workflow_name}>
                  {workflow.workflow_name}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm">
            <span className="mb-1 block font-medium">Worker Override (optional)</span>
            <select
              value={helperWorkerUuid}
              onChange={(event) => setHelperWorkerUuid(event.target.value)}
              className="w-full border rounded px-3 py-2 bg-white"
            >
              <option value="">Use current target / auto</option>
              {machines
                .filter((machine) => machine.machine_uuid)
                .map((machine) => (
                  <option key={machine.machine_uuid} value={machine.machine_uuid}>
                    {machine.machine_name ?? "unknown"} ({machine.machine_uuid})
                  </option>
                ))}
            </select>
          </label>

          <label className="text-sm">
            <span className="mb-1 block font-medium">Client Name</span>
            <input
              type="text"
              value={helperClientName}
              onChange={(event) => setHelperClientName(event.target.value)}
              className="w-full border rounded px-3 py-2 bg-white"
            />
          </label>

          <label className="text-sm">
            <span className="mb-1 block font-medium">Household Name</span>
            <input
              type="text"
              value={helperHouseholdName}
              onChange={(event) => setHelperHouseholdName(event.target.value)}
              className="w-full border rounded px-3 py-2 bg-white"
            />
          </label>

          <label className="text-sm">
            <span className="mb-1 block font-medium">Max Clients</span>
            <input
              type="number"
              min={1}
              value={helperMaxClients}
              onChange={(event) => setHelperMaxClients(event.target.value)}
              className="w-full border rounded px-3 py-2 bg-white"
            />
          </label>

          <label className="text-sm">
            <span className="mb-1 block font-medium">Max Pages</span>
            <input
              type="number"
              min={1}
              value={helperMaxPages}
              onChange={(event) => setHelperMaxPages(event.target.value)}
              className="w-full border rounded px-3 py-2 bg-white"
            />
          </label>
        </div>

        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={helperRetryFailedOnly}
            onChange={(event) => setHelperRetryFailedOnly(event.target.checked)}
          />
          Retry failed only
        </label>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void runGuidedCommand()}
            disabled={helperBusy || !helperWorkflow}
            className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50"
          >
            {helperBusy ? "Submitting..." : "Run Guided Command"}
          </button>
        </div>

        <div className="mt-4 border-t pt-3">
          <label className="text-sm">
            <span className="mb-1 block font-medium">Free-text fallback (optional)</span>
            <textarea
              value={helperFreeText}
              onChange={(event) => setHelperFreeText(event.target.value)}
              rows={3}
              placeholder="Example: run marketplace workflow on worker A max clients 25"
              className="w-full border rounded px-3 py-2 bg-white"
            />
          </label>
          <button
            type="button"
            onClick={() => void runFreeTextCommand()}
            disabled={helperBusy || !helperFreeText.trim()}
            className="mt-2 rounded border border-slate-300 bg-white px-4 py-2 text-slate-900 disabled:opacity-50"
          >
            Submit Free-Text Command
          </button>
        </div>

        {helperFeedback && (
          <p
            className={
              helperFeedback.kind === "success"
                ? "mt-3 rounded border border-emerald-300 bg-emerald-50 p-2 text-emerald-800"
                : "mt-3 rounded border border-red-300 bg-red-50 p-2 text-red-700"
            }
          >
            {helperFeedback.message} ({helperFeedback.timestamp})
          </p>
        )}
      </section>

      <section className="mt-8 border rounded p-4 bg-slate-50">
        <h2 className="text-xl font-semibold mb-3">Orchestration Brain</h2>
        <p className="text-sm text-slate-600 mb-3">
          Natural language command interface for workflow selection, worker selection, and status reasoning.
        </p>

        <div className="flex gap-2 mb-3">
          <input
            type="text"
            value={chatInput}
            onChange={(event) => setChatInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void submitBrainCommand();
              }
            }}
            placeholder="Type a command, e.g. 'Which worker is free?'"
            className="flex-1 border rounded px-3 py-2 bg-white"
          />
          <button
            type="button"
            onClick={() => void submitBrainCommand()}
            disabled={chatLoading}
            className="px-4 py-2 rounded bg-slate-900 text-white disabled:opacity-50"
          >
            {chatLoading ? "Thinking..." : "Send"}
          </button>
        </div>

        <div className="flex flex-wrap gap-2 mb-3 text-xs">
          {[
            "Which worker is free?",
            "What failed last?",
            "What is running now?",
            "List workflows",
            "Refresh HealthSherpa syncs",
            "Run Marketplace workflow on Worker A",
            "Retry last failed task",
          ].map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setChatInput(example)}
              className="px-2 py-1 rounded border bg-white hover:bg-slate-100"
            >
              {example}
            </button>
          ))}
        </div>

        <div className="max-h-72 overflow-auto border rounded bg-white p-3 space-y-2">
          {chatHistory.map((entry, index) => (
            <div key={`chat-${index}`} className={entry.role === "user" ? "text-right" : "text-left"}>
              <p className="text-xs font-semibold text-slate-500 mb-1">{entry.role === "user" ? "You" : "Bill"}</p>
              <pre className="whitespace-pre-wrap text-sm bg-slate-100 rounded p-2 inline-block text-left">
                {entry.message}
              </pre>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-8 border rounded p-4 bg-slate-50">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xl font-semibold">Brain Audit</h2>
          <button
            type="button"
            onClick={() => void loadBrainPanels()}
            className="rounded border bg-white px-3 py-1 text-sm"
          >
            Refresh
          </button>
        </div>

        {errors.audit ? (
          <p className="text-red-600">{errors.audit}</p>
        ) : auditEntries.length === 0 ? (
          <p>No audit entries yet.</p>
        ) : (
          <ul className="space-y-2">
            {auditEntries.map((entry, index) => (
              <li key={`audit-${index}`} className="rounded border bg-white p-3 text-sm">
                <p><strong>Time:</strong> {entry.timestamp ?? "-"}</p>
                <p><strong>Original:</strong> {entry.original_user_text ?? "-"}</p>
                <p><strong>Intent:</strong> {entry.interpreted_intent ?? "-"}</p>
                <p><strong>Workflow:</strong> {entry.selected_workflow ?? "-"}</p>
                <p><strong>Worker:</strong> {entry.selected_worker ?? "-"}</p>
                <p><strong>Task ID:</strong> {entry.queued_task_id ?? "-"}</p>
                <p><strong>Outcome:</strong> {entry.after_execution ?? "-"}</p>
                <p><strong>Explanation:</strong> {entry.before_execution ?? "-"}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
