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
  suggestedNextAction?: string;
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

const taskStatusLabel = (status?: string): string => {
  const normalized = (status ?? "").toLowerCase();
  if (normalized === "running") return "In progress";
  if (normalized === "assigned") return "Assigned";
  if (normalized === "queued") return "Queued";
  if (normalized === "completed") return "Completed";
  if (normalized === "failed") return "Failed";
  if (normalized === "canceled" || normalized === "cancelled") return "Canceled";
  return status ?? "Unknown";
};

const taskStatusClasses = (status?: string): string => {
  const normalized = (status ?? "").toLowerCase();
  if (normalized === "completed") return "bg-emerald-500/15 text-emerald-200 border border-emerald-400/30";
  if (normalized === "failed") return "bg-rose-500/15 text-rose-200 border border-rose-400/30";
  if (normalized === "running") return "bg-sky-500/15 text-sky-200 border border-sky-400/30";
  if (normalized === "queued" || normalized === "assigned") return "bg-amber-500/15 text-amber-200 border border-amber-400/30";
  return "bg-slate-700/60 text-slate-200 border border-slate-500/60";
};

const workerStatusClasses = (machine: Machine): string => {
  if (!machine.online) return "bg-slate-700/60 text-slate-300 border border-slate-600/80";

  const status = (machine.status ?? "").toLowerCase();
  if (status === "busy" || status === "running") {
    return "bg-amber-500/15 text-amber-200 border border-amber-400/30";
  }
  if (status === "idle") {
    return "bg-emerald-500/15 text-emerald-200 border border-emerald-400/30";
  }
  return "bg-sky-500/15 text-sky-200 border border-sky-400/30";
};

const workerStatusText = (machine: Machine): string => {
  if (!machine.online) return "Offline";

  const status = (machine.status ?? "unknown").toLowerCase();
  if (status === "idle") return "Online · Idle";
  if (status === "busy" || status === "running") return "Online · Busy";
  return `Online · ${machine.status ?? "Unknown"}`;
};

const shortTaskId = (id?: string): string => {
  if (!id) return "No ID";
  return id.length > 10 ? `${id.slice(0, 8)}...` : id;
};

const toDisplayTime = (value?: string): string => {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
};

const BUTTON_PRIMARY =
  "rounded-lg bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50";
const BUTTON_SECONDARY =
  "rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-cyan-400/70 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50";
const BUTTON_DANGER =
  "rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-1.5 text-xs text-rose-200 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-40";
const BUTTON_ACCENT_GHOST =
  "rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-200 transition hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-40";

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
  const activeTasks = tasks.filter((task) => activeTaskStatuses.has((task.status ?? "").toLowerCase()));
  const failedTasks = tasks.filter((task) => (task.status ?? "").toLowerCase() === "failed");
  const successfulTasks = tasks.filter((task) => (task.status ?? "").toLowerCase() === "completed");
  const onlineWorkers = machines.filter((machine) => machine.online);

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
          suggestedNextAction: body.suggested_next_action ?? undefined,
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
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#13324a_0%,_#090d14_45%,_#070a11_100%)] text-slate-100">
      <div className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6 lg:px-10">
        <header className="mb-6 rounded-2xl border border-slate-800/90 bg-slate-900/75 px-5 py-5 shadow-[0_22px_45px_-30px_rgba(8,145,178,0.7)] backdrop-blur">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-cyan-300">Bill Operations Control</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight">AI Workflow Command Center</h1>
              <p className="mt-2 text-sm text-slate-400">
                Calm, real-time control of workers, orchestration, and task execution.
              </p>
            </div>

            <div className="grid w-full gap-3 sm:grid-cols-2 lg:w-[540px]">
              <div className="rounded-xl border border-slate-800/90 bg-slate-900/90 px-4 py-3 shadow-[0_10px_24px_-18px_rgba(2,132,199,0.6)]">
                <p className="text-xs text-slate-400">Workers Online</p>
                <p className="mt-1 text-2xl font-semibold text-cyan-300">{onlineWorkers.length}</p>
              </div>
              <div className="rounded-xl border border-slate-800/90 bg-slate-900/90 px-4 py-3 shadow-[0_10px_24px_-18px_rgba(2,132,199,0.6)]">
                <p className="text-xs text-slate-400">Active Tasks</p>
                <p className="mt-1 text-2xl font-semibold text-cyan-300">{activeTasks.length}</p>
              </div>
              <div className="rounded-xl border border-slate-800/90 bg-slate-900/90 px-4 py-3 shadow-[0_10px_24px_-18px_rgba(244,63,94,0.45)]">
                <p className="text-xs text-slate-400">Failed Tasks</p>
                <p className="mt-1 text-2xl font-semibold text-rose-300">{failedTasks.length}</p>
              </div>
              <div className="rounded-xl border border-slate-800/90 bg-slate-900/90 px-4 py-3 shadow-[0_10px_24px_-18px_rgba(16,185,129,0.45)]">
                <p className="text-xs text-slate-400">Recent Successful Runs</p>
                <p className="mt-1 text-2xl font-semibold text-emerald-300">{successfulTasks.length}</p>
              </div>
            </div>
          </div>
        </header>

        {errors.config && (
          <div className="mb-6 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            {errors.config}
          </div>
        )}

        <section className="grid gap-6 lg:grid-cols-12">
          <div className="space-y-6 lg:col-span-4">
            <section className="rounded-2xl border border-cyan-500/25 bg-gradient-to-b from-slate-900/90 to-slate-900/70 p-5 shadow-[0_24px_45px_-30px_rgba(8,145,178,0.8)]">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">Brain Command Center</h2>
                  <p className="text-xs text-slate-400">Natural language control for Bill orchestration.</p>
                </div>
                <span className="rounded-full border border-cyan-400/40 bg-cyan-400/10 px-2.5 py-1 text-xs text-cyan-200">
                  Live
                </span>
              </div>

              <div className="rounded-xl border border-cyan-500/20 bg-slate-950/80 p-3 shadow-inner shadow-cyan-950/40">
                <textarea
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void submitBrainCommand();
                    }
                  }}
                  rows={4}
                  placeholder="Tell Bill what to do. Example: Run marketplace workflow on the best idle worker with max clients 25"
                  className="w-full resize-none rounded-lg border border-slate-700 bg-slate-900 px-3 py-3 text-sm leading-relaxed text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-500/30"
                />
                <div className="mt-3 flex justify-end">
                  <button
                    type="button"
                    onClick={() => void submitBrainCommand()}
                    disabled={chatLoading || !chatInput.trim()}
                    className={BUTTON_PRIMARY}
                  >
                    {chatLoading ? "Thinking..." : "Send Command"}
                  </button>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {[
                  "Which worker is free?",
                  "What is running now?",
                  "Show online workers",
                  "Retry last failed task",
                ].map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => setChatInput(example)}
                    className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 transition hover:border-cyan-400/60 hover:bg-cyan-500/10 hover:text-cyan-200"
                  >
                    {example}
                  </button>
                ))}
              </div>

              <div className="mt-4 max-h-[520px] space-y-3 overflow-auto pr-1">
                {chatHistory.map((entry, index) => (
                  <div
                    key={`chat-${index}`}
                    className={
                      entry.role === "user"
                        ? "ml-8 rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-3"
                        : "mr-8 rounded-xl border border-slate-700 bg-slate-900/90 p-3"
                    }
                  >
                    <p className="mb-2 text-[11px] uppercase tracking-wider text-slate-400">
                      {entry.role === "user" ? "You" : "Bill"}
                    </p>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-100">{entry.message}</p>
                    {entry.suggestedNextAction && (
                      <div className="mt-3 rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-100">
                        Suggested next action: {entry.suggestedNextAction}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          </div>

          <div className="space-y-6 lg:col-span-5">
            <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 shadow-lg shadow-black/25">
              <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <h2 className="text-lg font-semibold">Task Operations</h2>
                  <p className="text-xs text-slate-400">Run workflows, monitor progress, and recover quickly.</p>
                </div>

                <div className="min-w-[240px]">
                  <label htmlFor="target-machine" className="mb-1 block text-xs text-slate-400">Target Worker</label>
                  <select
                    id="target-machine"
                    value={targetMachineUuid}
                    onChange={(event) => setTargetMachineUuid(event.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-500/30"
                  >
                    <option value="">Auto assign best available</option>
                    {machines.map((machine) => {
                      if (!machine.machine_uuid) return null;
                      return (
                        <option key={machine.machine_uuid} value={machine.machine_uuid}>
                          {machine.machine_name ?? "unknown"} · {workerStatusText(machine)}
                        </option>
                      );
                    })}
                  </select>
                </div>
              </div>

              <div className="mb-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                <button
                  type="button"
                  onClick={createTestTask}
                  disabled={loading}
                  className={BUTTON_SECONDARY}
                >
                  {loading ? "Creating..." : "Create Test Task"}
                </button>
                <button
                  type="button"
                  onClick={createScreenshotTask}
                  disabled={loading}
                  className={BUTTON_SECONDARY}
                >
                  Screenshot Task
                </button>
                <button
                  type="button"
                  onClick={createVisibleWorkflowTask}
                  disabled={loading}
                  className={BUTTON_SECONDARY}
                >
                  Visible Workflow
                </button>
                <button
                  type="button"
                  onClick={runSmartSherpaSync}
                  disabled={loading}
                  className={BUTTON_PRIMARY}
                >
                  Run Smart Sherpa Sync
                </button>
              </div>

              {taskActionFeedback && (
                <div
                  className={
                    taskActionFeedback.kind === "success"
                      ? "mb-4 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200"
                      : "mb-4 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200"
                  }
                >
                  {taskActionFeedback.message} · {taskActionFeedback.timestamp}
                </div>
              )}

              {actionError && (
                <div className="mb-4 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                  {actionError}
                </div>
              )}

              {errors.tasks ? (
                <p className="text-sm text-rose-300">{errors.tasks}</p>
              ) : tasks.length === 0 ? (
                <p className="text-sm text-slate-400">No tasks yet. Start by running a command or workflow.</p>
              ) : (
                <div className="space-y-3">
                  {tasks.map((task, index) => {
                    const status = (task.status ?? "").toLowerCase();
                    const canCancel = !!task.id && activeTaskStatuses.has(status);
                    const canRetry = !!task.id && status === "failed";
                    const isSelected = selectedTask?.id === task.id;

                    return (
                      <div
                        key={task.id ?? `task-${index}`}
                        className={
                          isSelected
                            ? "rounded-xl border border-cyan-400/50 bg-slate-900/90 p-4"
                            : "rounded-xl border border-slate-800 bg-slate-900/60 p-4"
                        }
                      >
                        <button
                          type="button"
                          onClick={() => setSelectedTask(task)}
                          className="w-full text-left"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <p className="text-sm font-semibold">{task.payload?.task_type ?? "General Task"}</p>
                              <p className="mt-1 text-xs text-slate-400">
                                Task {shortTaskId(task.id)} · {toDisplayTime(task.created_at)}
                              </p>
                            </div>
                            <span className={`rounded-full px-2.5 py-1 text-xs ${taskStatusClasses(task.status)}`}>
                              {taskStatusLabel(task.status)}
                            </span>
                          </div>
                          <p className="mt-2 text-sm text-slate-300">
                            {task.error
                              ? `This run failed: ${task.error}`
                              : status === "completed"
                                ? "Completed successfully."
                                : status === "running"
                                  ? "Currently executing on a worker."
                                  : status === "queued"
                                    ? "Waiting for an available worker."
                                    : status === "assigned"
                                      ? "Assigned and waiting to begin."
                                      : "Awaiting status update."}
                          </p>
                          {task.assigned_machine_uuid && (
                            <p className="mt-1 text-xs text-slate-500">Worker: {task.assigned_machine_uuid}</p>
                          )}
                        </button>

                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={!canCancel || taskActionBusyKey !== null}
                            onClick={() => void cancelTask(task.id)}
                            className={BUTTON_DANGER}
                          >
                            {taskActionBusyKey === `cancel-${task.id}` ? "Canceling..." : "Cancel Task"}
                          </button>
                          <button
                            type="button"
                            disabled={!canRetry || taskActionBusyKey !== null}
                            onClick={() => void retryFailedTask(task)}
                            className={BUTTON_ACCENT_GHOST}
                          >
                            {taskActionBusyKey === `retry-${task.id}` ? "Retrying..." : "Retry Task"}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {selectedTask && (
                <details className="mt-4 rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                  <summary className="cursor-pointer text-sm font-medium text-slate-200">
                    Selected task details (expand technical details)
                  </summary>
                  <div className="mt-3 space-y-3 text-xs text-slate-300">
                    <p>Task ID: {selectedTask.id ?? "-"}</p>
                    <p>Status: {taskStatusLabel(selectedTask.status)}</p>
                    <p>Type: {selectedTask.payload?.task_type ?? "-"}</p>

                    <div>
                      <p className="mb-1 font-semibold text-slate-200">Downloaded files</p>
                      {(selectedTask.result_json?.downloads ?? []).length > 0 ? (
                        <ul className="list-disc pl-5">
                          {(selectedTask.result_json?.downloads ?? []).map((download, index) => (
                            <li key={`${selectedTask.id ?? "task"}-download-${index}`}>
                              {download.filename ?? "-"} · {download.local_path ?? "-"}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-slate-400">No downloaded files recorded.</p>
                      )}
                    </div>

                    <pre className="overflow-auto rounded-lg border border-slate-800 bg-slate-900 p-3 text-[11px] text-slate-300">
                      {JSON.stringify(selectedTask.result_json ?? {}, null, 2)}
                    </pre>
                  </div>
                </details>
              )}

              {response && (
                <details className="mt-4 rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                  <summary className="cursor-pointer text-sm font-medium text-slate-200">
                    Last API response
                  </summary>
                  <pre className="mt-3 overflow-auto rounded-lg border border-slate-800 bg-slate-900 p-3 text-[11px] text-slate-300">
                    {JSON.stringify(response, null, 2)}
                  </pre>
                </details>
              )}
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 shadow-lg shadow-black/25">
              <div className="mb-3">
                <h2 className="text-lg font-semibold">Workflow Command Builder</h2>
                <p className="text-xs text-slate-400">Structured inputs with free-text fallback.</p>
              </div>

              {errors.workflows && <p className="mb-3 text-sm text-rose-300">{errors.workflows}</p>}

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-xs text-slate-400">
                  Workflow
                  <select
                    value={helperWorkflow}
                    onChange={(event) => setHelperWorkflow(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-500/30"
                  >
                    {workflows.map((workflow) => (
                      <option key={workflow.workflow_name} value={workflow.workflow_name}>
                        {workflow.workflow_name}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="text-xs text-slate-400">
                  Worker override
                  <select
                    value={helperWorkerUuid}
                    onChange={(event) => setHelperWorkerUuid(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-500/30"
                  >
                    <option value="">Use selected / auto</option>
                    {machines
                      .filter((machine) => machine.machine_uuid)
                      .map((machine) => (
                        <option key={machine.machine_uuid} value={machine.machine_uuid}>
                          {machine.machine_name ?? "unknown"} · {workerStatusText(machine)}
                        </option>
                      ))}
                  </select>
                </label>

                <label className="text-xs text-slate-400">
                  Client name
                  <input
                    type="text"
                    value={helperClientName}
                    onChange={(event) => setHelperClientName(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-500/30"
                  />
                </label>

                <label className="text-xs text-slate-400">
                  Household name
                  <input
                    type="text"
                    value={helperHouseholdName}
                    onChange={(event) => setHelperHouseholdName(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-500/30"
                  />
                </label>

                <label className="text-xs text-slate-400">
                  Max clients
                  <input
                    type="number"
                    min={1}
                    value={helperMaxClients}
                    onChange={(event) => setHelperMaxClients(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-500/30"
                  />
                </label>

                <label className="text-xs text-slate-400">
                  Max pages
                  <input
                    type="number"
                    min={1}
                    value={helperMaxPages}
                    onChange={(event) => setHelperMaxPages(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-500/30"
                  />
                </label>
              </div>

              <label className="mt-3 flex items-center gap-2 text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={helperRetryFailedOnly}
                  onChange={(event) => setHelperRetryFailedOnly(event.target.checked)}
                  className="h-4 w-4 rounded border-slate-600 bg-slate-900"
                />
                Retry failed items only
              </label>

              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void runGuidedCommand()}
                  disabled={helperBusy || !helperWorkflow}
                  className={BUTTON_PRIMARY}
                >
                  {helperBusy ? "Submitting..." : "Run Guided Command"}
                </button>
              </div>

              <div className="mt-4 border-t border-slate-800 pt-4">
                <label className="text-xs text-slate-400">
                  Free-text fallback
                  <textarea
                    value={helperFreeText}
                    onChange={(event) => setHelperFreeText(event.target.value)}
                    rows={3}
                    placeholder="Example: run marketplace workflow on worker A max clients 25"
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-500/30"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => void runFreeTextCommand()}
                  disabled={helperBusy || !helperFreeText.trim()}
                  className={BUTTON_SECONDARY}
                >
                  Submit Free-text Command
                </button>
              </div>

              {helperFeedback && (
                <div
                  className={
                    helperFeedback.kind === "success"
                      ? "mt-4 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200"
                      : "mt-4 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200"
                  }
                >
                  {helperFeedback.message} · {helperFeedback.timestamp}
                </div>
              )}
            </section>
          </div>

          <div className="space-y-6 lg:col-span-3">
            <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 shadow-lg shadow-black/25">
              <h2 className="text-lg font-semibold">Workers</h2>
              <p className="mb-3 text-xs text-slate-400">Availability and assignment at a glance.</p>

              {errors.machines ? (
                <p className="text-sm text-rose-300">{errors.machines}</p>
              ) : machines.length === 0 ? (
                <p className="text-sm text-slate-400">No workers detected.</p>
              ) : (
                <div className="space-y-3">
                  {machines.map((machine, index) => {
                    const isSelected = !!machine.machine_uuid && machine.machine_uuid === targetMachineUuid;
                    return (
                      <div
                        key={machine.machine_uuid ?? `machine-${index}`}
                        className={
                          isSelected
                            ? "rounded-xl border border-cyan-400/50 bg-slate-900 p-3"
                            : "rounded-xl border border-slate-800 bg-slate-900/60 p-3"
                        }
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-sm font-medium">{machine.machine_name ?? machine.worker_name ?? "Unknown worker"}</p>
                            <p className="mt-1 text-[11px] text-slate-500">{shortTaskId(machine.machine_uuid)}</p>
                          </div>
                          <span className={`rounded-full px-2.5 py-1 text-[11px] ${workerStatusClasses(machine)}`}>
                            {workerStatusText(machine)}
                          </span>
                        </div>

                        {machine.current_task_id ? (
                          <p className="mt-2 text-xs text-slate-400">Current task: {shortTaskId(machine.current_task_id)}</p>
                        ) : (
                          <p className="mt-2 text-xs text-slate-500">No active task assigned.</p>
                        )}

                        <button
                          type="button"
                          onClick={() => setTargetMachineUuid(machine.machine_uuid ?? "")}
                          disabled={!machine.machine_uuid}
                          className="mt-3 w-full rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 transition hover:border-cyan-400/70 hover:bg-cyan-500/10 hover:text-cyan-200 disabled:opacity-40"
                        >
                          {isSelected ? "Selected for assignment" : "Select worker"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs text-slate-400">
                Health: {errors.health ? "Unavailable" : health?.status ?? "Unknown"}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 shadow-lg shadow-black/25">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">Audit Trail</h2>
                  <p className="text-xs text-slate-400">Recent command history and outcomes.</p>
                </div>
                <button
                  type="button"
                  onClick={() => void loadBrainPanels()}
                  className={BUTTON_SECONDARY}
                >
                  Refresh
                </button>
              </div>

              {errors.audit ? (
                <p className="text-sm text-rose-300">{errors.audit}</p>
              ) : auditEntries.length === 0 ? (
                <p className="text-sm text-slate-400">No command history yet.</p>
              ) : (
                <div className="max-h-[520px] space-y-2 overflow-auto pr-1">
                  {auditEntries.map((entry, index) => (
                    <article key={`audit-${index}`} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                      <p className="text-xs text-slate-500">{toDisplayTime(entry.timestamp)}</p>
                      <p className="mt-1 text-sm text-slate-200">{entry.original_user_text ?? "-"}</p>
                      <p className="mt-2 text-xs text-slate-400">
                        Intent: <span className="text-slate-300">{entry.interpreted_intent ?? "-"}</span>
                        {" · "}
                        Workflow: <span className="text-slate-300">{entry.selected_workflow ?? "-"}</span>
                      </p>
                      <p className="mt-1 text-xs text-slate-400">
                        Worker: <span className="text-slate-300">{entry.selected_worker ?? "-"}</span>
                        {" · "}
                        Task: <span className="text-slate-300">{entry.queued_task_id ?? "-"}</span>
                      </p>
                      <p className="mt-2 text-sm text-slate-300">{entry.after_execution ?? "No outcome recorded."}</p>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}
