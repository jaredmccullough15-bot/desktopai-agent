"use client";

import { useEffect, useRef, useState } from "react";

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
  drafts?: string;
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
  requires_confirmation?: boolean;
  pending_interaction_id?: string | null;
  pending_questions?: string[];
  live_reasoning?: string[];
  task?: BrainTaskRef | null;
};

type DraftVariableInput = {
  field_key: string;
  sample_value: string;
  is_variable: boolean;
  required_input: boolean;
  input_source: string;
  source_detail: string;
  prompt_question: string;
};

type DraftFieldMapping = {
  field: string;
  source: string;
  source_detail: string;
};

type DraftStep = {
  step_order: number;
  name: string;
  step_name: string;
  purpose: string;
  instruction: string;
  action: string;
  selector: string;
  url: string;
  value: string;
  option: string;
  manual_review_required: boolean;
  variable_inputs: DraftVariableInput[];
  field_mappings: DraftFieldMapping[];
  validation_rules: string[];
  intent: string;
  description: string;
  success_condition: string;
  failure_condition: string;
  failure_behavior: string;
  recovery_strategy: string;
};

type WorkflowLearningDraft = {
  draft_id: string;
  created_at: string;
  updated_at: string;
  learning_path: string;
  workflow_name: string;
  goal: string;
  description: string;
  required_inputs: string[];
  required_session_state: string[];
  safe_for_unattended: boolean;
  steps: DraftStep[];
  validation_rules: string[];
  fallback_strategies: string[];
  common_failures: string[];
  review_status: string;
  reviewer_notes?: string | null;
  published_workflow_name?: string | null;
  variables?: Array<Record<string, unknown>>;
  teaching_complete?: boolean;
  teaching_pending_step?: number | null;
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

type TeachingStepQuestionItem = {
  step_order: number;
  field: string;
  question: string;
  current_value: string | null;
  options: string[];
};

type TeachingSessionQuestion = {
  draft_id: string;
  step_order: number;
  step_name: string;
  questions: TeachingStepQuestionItem[];
  teaching_complete: boolean;
  steps_remaining: number;
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
  const [learningPath, setLearningPath] = useState("plain_english");
  const [learningWorkflowName, setLearningWorkflowName] = useState("");
  const [learningGoal, setLearningGoal] = useState("");
  const [learningSourceText, setLearningSourceText] = useState("");
  const [workflowDrafts, setWorkflowDrafts] = useState<WorkflowLearningDraft[]>([]);
  const [expandedDraftId, setExpandedDraftId] = useState<string | null>(null);
  const [draftStepEdits, setDraftStepEdits] = useState<Record<string, DraftStep[]>>({});
  const [learningBusyKey, setLearningBusyKey] = useState<string | null>(null);
  const [learningFeedback, setLearningFeedback] = useState<ActionFeedback | null>(null);
  const [teachingSessionDraftId, setTeachingSessionDraftId] = useState<string | null>(null);
  const [teachingOverlayOpen, setTeachingOverlayOpen] = useState(false);
  const [teachingStatus, setTeachingStatus] = useState<"watching" | "step_captured" | "waiting_clarification" | "paused">("watching");
  const [teachingCurrentQuestion, setTeachingCurrentQuestion] = useState<TeachingSessionQuestion | null>(null);
  const [teachingAnswers, setTeachingAnswers] = useState<Record<string, string>>({});
  const [teachingStartUrl, setTeachingStartUrl] = useState<string>("");
  const [teachingLaunchStatus, setTeachingLaunchStatus] = useState<null | "launching" | "running" | "error">(null);
  const [teachingLaunchPid, setTeachingLaunchPid] = useState<number | null>(null);
  const prevTeachingStepCountRef = useRef<number>(0);
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

  const toDraftVariableInput = (item: Partial<DraftVariableInput> | undefined, fallbackField: string): DraftVariableInput => ({
    field_key: String(item?.field_key ?? fallbackField).trim() || fallbackField,
    sample_value: String(item?.sample_value ?? "").trim(),
    is_variable: Boolean(item?.is_variable ?? true),
    required_input: Boolean(item?.required_input ?? true),
    input_source: String(item?.input_source ?? "ask_user").trim() || "ask_user",
    source_detail: String(item?.source_detail ?? "").trim(),
    prompt_question: String(item?.prompt_question ?? `How should ${fallbackField} be populated?`).trim(),
  });

  const toDraftFieldMapping = (item: Partial<DraftFieldMapping> | undefined, fallbackField: string): DraftFieldMapping => ({
    field: String(item?.field ?? fallbackField).trim() || fallbackField,
    source: String(item?.source ?? "ask_user").trim() || "ask_user",
    source_detail: String(item?.source_detail ?? "").trim(),
  });

  const toDraftStep = (step: Partial<DraftStep>, index: number): DraftStep => {
    const selector = String(step.selector ?? "").trim();
    const fallbackField = selector || `step_${index + 1}_value`;
    const variableInputsRaw = Array.isArray(step.variable_inputs) ? step.variable_inputs : [];
    const fieldMappingsRaw = Array.isArray(step.field_mappings) ? step.field_mappings : [];
    return {
      step_order: Number(step.step_order ?? index + 1),
      name: String(step.name ?? `step_${index + 1}`).trim() || `step_${index + 1}`,
      step_name: String(step.step_name ?? step.name ?? `Step ${index + 1}`).trim() || `Step ${index + 1}`,
      purpose: String(step.purpose ?? "").trim(),
      instruction: String(step.instruction ?? "").trim(),
      action: String(step.action ?? "manual_step").trim() || "manual_step",
      selector,
      url: String(step.url ?? "").trim(),
      value: String(step.value ?? "").trim(),
      option: String(step.option ?? "").trim(),
      manual_review_required: Boolean(step.manual_review_required),
      variable_inputs: variableInputsRaw.map((item) => toDraftVariableInput(item, fallbackField)),
      field_mappings: fieldMappingsRaw.map((item) => toDraftFieldMapping(item, fallbackField)),
      validation_rules: Array.isArray(step.validation_rules) ? step.validation_rules.map((rule) => String(rule)) : [],
      success_condition: String(step.success_condition ?? "").trim(),
      failure_behavior: String(step.failure_behavior ?? "").trim(),
      intent: String(step.intent ?? "").trim(),
      description: String(step.description ?? "").trim(),
      failure_condition: String(step.failure_condition ?? "").trim(),
      recovery_strategy: String(step.recovery_strategy ?? "").trim(),
    };
  };

  const cloneDraftSteps = (steps: DraftStep[] | Array<Record<string, unknown>>): DraftStep[] =>
    (steps ?? []).map((step, index) => toDraftStep(step as DraftStep, index));

  const ensureDraftEditingState = (draft: WorkflowLearningDraft) => {
    setDraftStepEdits((current) => {
      if (current[draft.draft_id]) {
        return current;
      }
      return { ...current, [draft.draft_id]: cloneDraftSteps(draft.steps) };
    });
  };

  const getDraftStepsForDisplay = (draft: WorkflowLearningDraft): DraftStep[] =>
    draftStepEdits[draft.draft_id] ?? cloneDraftSteps(draft.steps);

  const updateDraftStep = (draftId: string, stepIndex: number, patch: Partial<DraftStep>) => {
    setDraftStepEdits((current) => {
      const existing = current[draftId] ? [...current[draftId]] : [];
      if (!existing[stepIndex]) {
        return current;
      }
      existing[stepIndex] = { ...existing[stepIndex], ...patch };
      return { ...current, [draftId]: existing };
    });
  };

  const updateDraftStepVariable = (
    draftId: string,
    stepIndex: number,
    variableIndex: number,
    patch: Partial<DraftVariableInput>,
  ) => {
    setDraftStepEdits((current) => {
      const existing = current[draftId] ? [...current[draftId]] : [];
      if (!existing[stepIndex]) {
        return current;
      }
      const variables = [...(existing[stepIndex].variable_inputs ?? [])];
      if (!variables[variableIndex]) {
        return current;
      }
      variables[variableIndex] = { ...variables[variableIndex], ...patch };
      existing[stepIndex] = { ...existing[stepIndex], variable_inputs: variables };
      return { ...current, [draftId]: existing };
    });
  };

  const draftStepSummary = (step: Record<string, unknown>, index: number): string => {
    const action = String(step.action ?? step.type ?? "manual_step").trim().toLowerCase();
    const instruction = String(step.instruction ?? "").trim();
    const selector = String(step.selector ?? "").trim();
    const url = String(step.url ?? "").trim();
    const value = String(step.value ?? "").trim();
    const name = String(step.name ?? `step_${index + 1}`).trim();

    if (instruction && action === "manual_step") {
      return `Manual step: ${instruction}`;
    }

    if (action === "open_url") {
      return url ? `Open ${url}` : "Open the target page";
    }

    if (action === "wait_for_element") {
      return selector ? `Wait until ${selector} appears` : "Wait for the page to be ready";
    }

    if (action === "click_selector") {
      return selector ? `Click ${selector}` : "Click the required on-screen element";
    }

    if (action === "type_text") {
      if (selector && value) return `Type \"${value}\" into ${selector}`;
      if (selector) return `Enter required text into ${selector}`;
      return "Enter the required text in the form";
    }

    if (action === "take_screenshot") {
      return "Capture a screenshot";
    }

    if (instruction) {
      return instruction;
    }

    return `Perform ${name.replaceAll("_", " ")}`;
  };

  const draftStepExtraDetail = (step: Record<string, unknown>): string => {
    const action = String(step.action ?? step.type ?? "manual_step").trim().toLowerCase();
    const instruction = String(step.instruction ?? "").trim();
    const selector = String(step.selector ?? "").trim();
    const url = String(step.url ?? "").trim();
    const value = String(step.value ?? "").trim();
    const manualRequired = Boolean(step.manual_review_required);

    const details: string[] = [];
    if (instruction && action !== "manual_step") details.push(`Instruction: ${instruction}`);
    if (selector) details.push(`Selector: ${selector}`);
    if (url) details.push(`URL: ${url}`);
    if (value) details.push(`Value: ${value}`);
    if (manualRequired) details.push("Needs manual review before unattended run");

    return details.join(" | ");
  };

  const saveDraftStructure = async (draft: WorkflowLearningDraft) => {
    if (learningBusyKey) {
      return;
    }

    const editedSteps = draftStepEdits[draft.draft_id] ?? cloneDraftSteps(draft.steps);
    const requiredInputs = editedSteps
      .flatMap((step) => step.variable_inputs ?? [])
      .filter((item) => item.required_input)
      .map((item) => item.field_key.trim())
      .filter((field, index, list) => field.length > 0 && list.indexOf(field) === index);

    setLearningBusyKey(`save-structure-${draft.draft_id}`);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const url = `${apiBase}/api/brain/workflow-learning/drafts/${draft.draft_id}/structure`;
      const response = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          steps: editedSteps,
          required_inputs: requiredInputs,
        }),
      });

      const body = (await response.json()) as WorkflowLearningDraft | { detail?: string };
      if (!response.ok) {
        throw new Error((body as { detail?: string }).detail ?? `Save structure failed (${response.status})`);
      }

      setFeedback(setLearningFeedback, "success", `Saved structured draft for ${draft.workflow_name}.`);
      await loadBrainPanels();
      setDraftStepEdits((current) => {
        const next = { ...current };
        next[draft.draft_id] = cloneDraftSteps((body as WorkflowLearningDraft).steps);
        return next;
      });
    } catch (error) {
      setFeedback(
        setLearningFeedback,
        "error",
        `Save structure failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setLearningBusyKey(null);
    }
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
    const draftsUrl = `${apiBase}/api/brain/workflow-learning/drafts?limit=100`;
    const [workflowsResult, auditResult, draftsResult] = await Promise.allSettled([
      fetchJson<WorkflowRecord[]>(workflowsUrl),
      fetchJson<BrainAuditEntry[]>(auditUrl),
      fetchJson<WorkflowLearningDraft[]>(draftsUrl),
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

      if (draftsResult.status === "fulfilled") {
        setWorkflowDrafts(Array.isArray(draftsResult.value) ? draftsResult.value : []);
        delete next.drafts;
      } else {
        next.drafts = `Workflow drafts fetch failed: ${String(draftsResult.reason)}`;
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

  const createWorkflowDraft = async () => {
    const normalizedName = learningWorkflowName.trim();
    const normalizedGoal = learningGoal.trim();
    const normalizedSource = learningSourceText.trim();
    const isDemonstrationPath = learningPath === "demonstration";

    if (learningBusyKey) {
      return;
    }

    if (!normalizedName) {
      return;
    }

    if (!isDemonstrationPath && !normalizedSource) {
      return;
    }

    setLearningBusyKey("create-draft");
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const url = `${apiBase}/api/brain/workflow-learning/drafts`;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          learning_path: learningPath,
          source_text: normalizedSource || undefined,
          workflow_name: normalizedName || undefined,
          goal: normalizedGoal || undefined,
        }),
      });
      const body = (await response.json()) as WorkflowLearningDraft | { detail?: string };
      if (!response.ok) {
        throw new Error((body as { detail?: string }).detail ?? `Draft creation failed (${response.status})`);
      }

      setFeedback(
        setLearningFeedback,
        "success",
        isDemonstrationPath
          ? `Started teaching draft ${(body as WorkflowLearningDraft).draft_id} for ${(body as WorkflowLearningDraft).workflow_name}. Waiting for real demonstration capture.`
          : `Created draft ${(body as WorkflowLearningDraft).draft_id} for ${(body as WorkflowLearningDraft).workflow_name}`,
      );
      startTeachingSession((body as WorkflowLearningDraft).draft_id);
      setLearningSourceText("");
      await loadBrainPanels();
    } catch (error) {
      setFeedback(
        setLearningFeedback,
        "error",
        `Create draft failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setLearningBusyKey(null);
    }
  };

  const updateDraftStatus = async (draftId: string, status: string) => {
    if (!draftId || learningBusyKey) {
      return;
    }
    setLearningBusyKey(`status-${draftId}`);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const url = `${apiBase}/api/brain/workflow-learning/drafts/${draftId}/status`;
      const response = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ review_status: status }),
      });
      const body = (await response.json()) as WorkflowLearningDraft | { detail?: string };
      if (!response.ok) {
        throw new Error((body as { detail?: string }).detail ?? `Status update failed (${response.status})`);
      }

      setFeedback(setLearningFeedback, "success", `Draft ${draftId} set to ${status}.`);
      await loadBrainPanels();
    } catch (error) {
      setFeedback(
        setLearningFeedback,
        "error",
        `Update draft status failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setLearningBusyKey(null);
    }
  };

  const deleteDraft = async (draftId: string, workflowName: string) => {
    if (!draftId || learningBusyKey) {
      return;
    }

    const confirmed = window.confirm(`Delete draft \"${workflowName}\"? This cannot be undone.`);
    if (!confirmed) {
      return;
    }

    setLearningBusyKey(`delete-${draftId}`);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const url = `${apiBase}/api/brain/workflow-learning/drafts/${draftId}`;
      const response = await fetch(url, { method: "DELETE" });
      if (!response.ok) {
        const body = (await response.json()) as { detail?: string };
        throw new Error(body.detail ?? `Delete draft failed (${response.status})`);
      }

      setExpandedDraftId((current) => (current === draftId ? null : current));
      setFeedback(setLearningFeedback, "success", `Deleted draft ${workflowName}.`);
      await loadBrainPanels();
    } catch (error) {
      setFeedback(
        setLearningFeedback,
        "error",
        `Delete draft failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setLearningBusyKey(null);
    }
  };

  const testDraftGuided = async (draftId: string) => {
    if (!draftId || learningBusyKey) {
      return;
    }
    setLearningBusyKey(`test-${draftId}`);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const targetWorker = helperWorkerUuid || targetMachineUuid || undefined;
      const url = `${apiBase}/api/brain/workflow-learning/drafts/${draftId}/test`;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_machine_uuid: targetWorker,
          guided_mode: true,
        }),
      });
      const body = (await response.json()) as TaskCreateResponse | { detail?: string };
      if (!response.ok) {
        throw new Error((body as { detail?: string }).detail ?? `Draft test failed (${response.status})`);
      }

      setFeedback(
        setLearningFeedback,
        "success",
        `Draft test queued as task ${(body as TaskCreateResponse).id ?? "unknown"}.`,
      );
      await loadDashboardData();
      await loadBrainPanels();
    } catch (error) {
      setFeedback(
        setLearningFeedback,
        "error",
        `Draft test failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setLearningBusyKey(null);
    }
  };

  const publishDraft = async (draftId: string) => {
    if (!draftId || learningBusyKey) {
      return;
    }
    setLearningBusyKey(`publish-${draftId}`);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const url = `${apiBase}/api/brain/workflow-learning/drafts/${draftId}/publish`;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved_by: "bill-web-operator" }),
      });
      const body = (await response.json()) as WorkflowLearningDraft | { detail?: string };
      if (!response.ok) {
        throw new Error((body as { detail?: string }).detail ?? `Publish failed (${response.status})`);
      }

      setFeedback(setLearningFeedback, "success", `Draft ${draftId} published.`);
      await loadDashboardData();
      await loadBrainPanels();
    } catch (error) {
      setFeedback(
        setLearningFeedback,
        "error",
        `Publish failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setLearningBusyKey(null);
    }
  };

  const loadTeachingQuestion = async (draftId: string) => {
    if (learningBusyKey) {
      return;
    }
    setLearningBusyKey(`teach-load-${draftId}`);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }
      const url = `${apiBase}/api/brain/workflow-learning/drafts/${draftId}/teach`;
      const response = await fetch(url);
      const body = (await response.json()) as TeachingSessionQuestion | { detail?: string };
      if (!response.ok) {
        throw new Error(
          (body as { detail?: string }).detail ?? `Fetch teaching question failed (${response.status})`,
        );
      }
      const question = body as TeachingSessionQuestion;
      setTeachingCurrentQuestion(question);
      setTeachingAnswers({});
      setTeachingStatus(question.teaching_complete ? "watching" : "waiting_clarification");
    } catch (error) {
      setFeedback(
        setLearningFeedback,
        "error",
        `Teaching question fetch failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setLearningBusyKey(null);
    }
  };

  const startTeachingSession = (draftId: string) => {
    setTeachingSessionDraftId(draftId);
    setTeachingOverlayOpen(true);
    setTeachingStatus("watching");
    setTeachingCurrentQuestion(null);
    setTeachingAnswers({});
  };

  const submitTeachingAnswers = async () => {
    if (!teachingSessionDraftId || !teachingCurrentQuestion || learningBusyKey) {
      return;
    }
    const answers = teachingCurrentQuestion.questions.map((q) => ({
      field: q.field,
      value: teachingAnswers[q.field] ?? q.current_value ?? "",
    }));
    setLearningBusyKey(`teach-submit-${teachingSessionDraftId}`);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }
      const url = `${apiBase}/api/brain/workflow-learning/drafts/${teachingSessionDraftId}/teach`;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step_order: teachingCurrentQuestion.step_order, answers }),
      });
      const body = (await response.json()) as TeachingSessionQuestion | { detail?: string };
      if (!response.ok) {
        throw new Error(
          (body as { detail?: string }).detail ?? `Submit teaching answers failed (${response.status})`,
        );
      }
      const next = body as TeachingSessionQuestion;
      setTeachingCurrentQuestion(next);
      setTeachingAnswers({});
      setTeachingStatus("step_captured");
      setTimeout(() => {
        setTeachingStatus(next.teaching_complete ? "watching" : "waiting_clarification");
      }, 1200);
      await loadBrainPanels();
    } catch (error) {
      setFeedback(
        setLearningFeedback,
        "error",
        `Submit answers failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
      setTeachingStatus("waiting_clarification");
    } finally {
      setLearningBusyKey(null);
    }
  };

  const pauseResumeTeaching = () => {
    setTeachingStatus((prev) => {
      if (prev === "paused") {
        return teachingCurrentQuestion && !teachingCurrentQuestion.teaching_complete
          ? "waiting_clarification"
          : "watching";
      }
      return "paused";
    });
  };

  const finishTeachingSession = async () => {
    setTeachingSessionDraftId(null);
    setTeachingOverlayOpen(false);
    setTeachingCurrentQuestion(null);
    setTeachingAnswers({});
    setTeachingStatus("watching");
    await loadBrainPanels();
  };

  const launchTeachBrowser = async () => {
    if (!teachingSessionDraftId) return;
    const apiBase = getApiBase();
    if (!apiBase) return;
    setTeachingLaunchStatus("launching");
    try {
      const res = await fetch(
        `${apiBase}/api/brain/workflow-learning/drafts/${teachingSessionDraftId}/teach-session/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ start_url: teachingStartUrl.trim(), api_base: apiBase }),
        },
      );
      const data = (await res.json()) as { pid?: number; status?: string; detail?: string };
      if (!res.ok) throw new Error(data.detail ?? `Launch failed (${res.status})`);
      setTeachingLaunchPid(data.pid ?? null);
      setTeachingLaunchStatus("running");
    } catch (err) {
      setTeachingLaunchStatus("error");
      setFeedback(
        setLearningFeedback,
        "error",
        `Browser launch failed: ${err instanceof Error ? err.message : "Unknown error"}`,
      );
    }
  };

  // Faster poll (2 s) while a teach session is active
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!teachingSessionDraftId) return;
    const id = setInterval(() => { void loadBrainPanels(); }, 2000);
    return () => clearInterval(id);
  }, [teachingSessionDraftId]);

  // Flash "step_captured" when the Playwright script appends a new step
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!teachingSessionDraftId) return;
    const count =
      workflowDrafts.find((d) => d.draft_id === teachingSessionDraftId)?.steps?.length ?? 0;
    if (count > prevTeachingStepCountRef.current && prevTeachingStepCountRef.current > 0) {
      setTeachingStatus("step_captured");
      setTimeout(() => {
        setTeachingStatus((prev) => (prev === "step_captured" ? "watching" : prev));
      }, 1500);
    }
    prevTeachingStepCountRef.current = count;
  }, [workflowDrafts, teachingSessionDraftId]);

  const teachingActiveDraft = teachingSessionDraftId
    ? (workflowDrafts.find((d) => d.draft_id === teachingSessionDraftId) ?? null)
    : null;

  const teachingStatusDot =
    teachingStatus === "step_captured"
      ? "bg-emerald-400"
      : teachingStatus === "waiting_clarification"
        ? "bg-cyan-400 animate-pulse"
        : teachingStatus === "paused"
          ? "bg-slate-400"
          : "bg-amber-400 animate-pulse";

  const teachingStatusLabel =
    teachingStatus === "step_captured"
      ? "Step Captured"
      : teachingStatus === "waiting_clarification"
        ? "Awaiting Answer"
        : teachingStatus === "paused"
          ? "Paused"
          : "Watching";

  const teachingStatusRing =
    teachingStatus === "step_captured"
      ? "border-emerald-400/50 bg-emerald-500/10"
      : teachingStatus === "waiting_clarification"
        ? "border-cyan-400/50 bg-cyan-500/10"
        : teachingStatus === "paused"
          ? "border-slate-500/50 bg-slate-800/70"
          : "border-amber-500/40 bg-amber-500/10";

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

            <section className="rounded-2xl border border-amber-500/30 bg-slate-900/75 p-5 shadow-lg shadow-black/25">
              <div className="mb-3">
                <h2 className="text-lg font-semibold">Teach Bill a Workflow</h2>
                <p className="text-xs text-slate-400">
                  Training experience: teach Bill like a human operator, test step-by-step, then approve and publish.
                </p>
              </div>

              <div className="mb-4 rounded-xl border border-cyan-400/30 bg-cyan-500/10 p-3 text-xs text-cyan-100">
                <p className="font-semibold">Training Stages</p>
                <p className="mt-1">1) Workflow Setup · 2) Teaching Mode · 3) Step Builder · 4) Validation · 5) Failure Behavior · 6) Test Mode · 7) Publish</p>
              </div>

              <div className="mb-3 grid gap-3 sm:grid-cols-2">
                <label className="flex items-center gap-2 text-xs text-slate-300">
                  <input type="checkbox" className="h-4 w-4 rounded border-slate-600 bg-slate-900" defaultChecked />
                  Login required
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-300">
                  <input type="checkbox" className="h-4 w-4 rounded border-slate-600 bg-slate-900" defaultChecked />
                  Visible mode required
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-300">
                  <input type="checkbox" className="h-4 w-4 rounded border-slate-600 bg-slate-900" />
                  Safe for unattended
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-300">
                  <input type="checkbox" className="h-4 w-4 rounded border-slate-600 bg-slate-900" />
                  Includes manual confirmations
                </label>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-xs text-slate-400">
                  Teaching path
                  <select
                    value={learningPath}
                    onChange={(event) => setLearningPath(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-amber-400/70 focus:ring-2 focus:ring-amber-500/30"
                  >
                    <option value="plain_english">Describe workflow</option>
                    <option value="demonstration">Demonstration / observed run</option>
                    <option value="sop_checklist">Import SOP / checklist</option>
                  </select>
                </label>

                <label className="text-xs text-slate-400">
                  Workflow name
                  <input
                    type="text"
                    value={learningWorkflowName}
                    onChange={(event) => setLearningWorkflowName(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-amber-400/70 focus:ring-2 focus:ring-amber-500/30"
                  />
                </label>
              </div>

              <label className="mt-3 block text-xs text-slate-400">
                Goal
                <input
                  type="text"
                  value={learningGoal}
                  onChange={(event) => setLearningGoal(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-amber-400/70 focus:ring-2 focus:ring-amber-500/30"
                />
              </label>

              <label className="mt-3 block text-xs text-slate-400">
                Teaching notes / observed run details
                <textarea
                  rows={6}
                  value={learningSourceText}
                  onChange={(event) => setLearningSourceText(event.target.value)}
                  placeholder={
                    learningPath === "demonstration"
                      ? "Optional notes. Start Teaching will open an empty draft and wait for real captured steps."
                      : "Describe steps line-by-line, paste checklist, or summarize observed run."
                  }
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-amber-400/70 focus:ring-2 focus:ring-amber-500/30"
                />
              </label>

              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void createWorkflowDraft()}
                  disabled={
                    learningBusyKey !== null ||
                    !learningWorkflowName.trim() ||
                    (learningPath !== "demonstration" && !learningSourceText.trim())
                  }
                  className={BUTTON_PRIMARY}
                >
                  {learningBusyKey === "create-draft" ? "Starting..." : "Start Teaching Mode"}
                </button>
              </div>

              {learningPath === "demonstration" && (
                <p className="mt-2 text-xs text-cyan-200/90">
                  Demonstration mode now ignores setup form text as workflow steps. It starts an empty draft and waits for actual captured actions.
                </p>
              )}

              {errors.drafts && <p className="mt-3 text-sm text-rose-300">{errors.drafts}</p>}

              {learningFeedback && (
                <div
                  className={
                    learningFeedback.kind === "success"
                      ? "mt-3 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200"
                      : "mt-3 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200"
                  }
                >
                  {learningFeedback.message} · {learningFeedback.timestamp}
                </div>
              )}

              <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100/90">
                Draft cards below show parsed steps from the teaching input (snapshot at draft update time). For live per-click capture while you perform the workflow,
                use the desktop app Teach Bill panel.
              </p>

              <div className="mt-4 max-h-[360px] space-y-3 overflow-auto pr-1">
                {workflowDrafts.length === 0 ? (
                  <p className="text-sm text-slate-400">No workflow drafts yet.</p>
                ) : (
                  workflowDrafts.map((draft) => (
                    <article key={draft.draft_id} className={`rounded-xl border p-3 ${teachingSessionDraftId === draft.draft_id ? "border-amber-500/40 bg-amber-950/20" : "border-slate-800 bg-slate-950/70"}`}>
                      <p className="text-sm font-semibold text-slate-100">{draft.workflow_name}</p>
                      <p className="mt-1 text-xs text-slate-400">
                        Teaching path: {draft.learning_path} · Status: {draft.review_status} · Updated: {toDisplayTime(draft.updated_at)}
                      </p>
                      <p className="mt-2 text-xs text-slate-300">{draft.goal}</p>
                      <div className="mt-2 flex items-center justify-between gap-2">
                        <p className="text-xs text-slate-500">Parsed steps: {draft.steps.length}</p>
                        <button
                          type="button"
                          onClick={() => {
                            ensureDraftEditingState(draft);
                            setExpandedDraftId((current) => (current === draft.draft_id ? null : draft.draft_id));
                          }}
                          className={BUTTON_ACCENT_GHOST}
                        >
                          {expandedDraftId === draft.draft_id ? "Hide Steps" : "View Steps"}
                        </button>
                      </div>

                      {expandedDraftId === draft.draft_id && (
                        <div className="mt-2 rounded-lg border border-slate-800 bg-slate-900/80 p-2">
                          {getDraftStepsForDisplay(draft).length === 0 ? (
                            <p className="text-xs text-slate-400">No parsed steps yet.</p>
                          ) : (
                            <div className="space-y-3 text-xs text-slate-200">
                              {getDraftStepsForDisplay(draft).map((step, idx) => (
                                <div key={`${draft.draft_id}-step-${idx}`} className="rounded border border-slate-800 bg-slate-950/70 px-2 py-2">
                                  <p className="font-medium text-slate-100">
                                    {idx + 1}. {draftStepSummary(step, idx)}
                                  </p>
                                  {draftStepExtraDetail(step) && (
                                    <p className="mt-1 text-[11px] text-slate-400">{draftStepExtraDetail(step)}</p>
                                  )}

                                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                                    <label className="text-[11px] text-slate-400">
                                      Step name
                                      <input
                                        type="text"
                                        value={step.step_name}
                                        onChange={(event) =>
                                          updateDraftStep(draft.draft_id, idx, { step_name: event.target.value })
                                        }
                                        className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                                      />
                                    </label>
                                    <label className="text-[11px] text-slate-400">
                                      Detected action
                                      <input
                                        type="text"
                                        value={step.action}
                                        readOnly
                                        className="mt-1 w-full rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-300"
                                      />
                                    </label>
                                  </div>

                                  <label className="mt-2 block text-[11px] text-slate-400">
                                    Step purpose
                                    <textarea
                                      rows={2}
                                      value={step.purpose}
                                      onChange={(event) =>
                                        updateDraftStep(draft.draft_id, idx, { purpose: event.target.value })
                                      }
                                      className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                                    />
                                  </label>

                                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                                    <label className="text-[11px] text-slate-400">
                                      Success condition
                                      <input
                                        type="text"
                                        value={step.success_condition}
                                        onChange={(event) =>
                                          updateDraftStep(draft.draft_id, idx, { success_condition: event.target.value })
                                        }
                                        className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                                      />
                                    </label>
                                    <label className="text-[11px] text-slate-400">
                                      Failure behavior
                                      <input
                                        type="text"
                                        value={step.failure_behavior}
                                        onChange={(event) =>
                                          updateDraftStep(draft.draft_id, idx, { failure_behavior: event.target.value })
                                        }
                                        className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                                      />
                                    </label>
                                  </div>

                                  {step.variable_inputs.length > 0 && (
                                    <div className="mt-2 rounded border border-cyan-500/20 bg-cyan-500/5 p-2">
                                      <p className="text-[11px] font-semibold text-cyan-100">Variable inputs</p>
                                      {step.variable_inputs.map((variable, variableIdx) => (
                                        <div key={`${draft.draft_id}-step-${idx}-var-${variableIdx}`} className="mt-2 rounded border border-slate-800 bg-slate-900/70 p-2">
                                          <label className="text-[11px] text-slate-400">
                                            Field key
                                            <input
                                              type="text"
                                              value={variable.field_key}
                                              onChange={(event) =>
                                                updateDraftStepVariable(draft.draft_id, idx, variableIdx, { field_key: event.target.value })
                                              }
                                              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                                            />
                                          </label>

                                          <label className="mt-2 block text-[11px] text-slate-400">
                                            Clarifying question
                                            <input
                                              type="text"
                                              value={variable.prompt_question}
                                              onChange={(event) =>
                                                updateDraftStepVariable(draft.draft_id, idx, variableIdx, {
                                                  prompt_question: event.target.value,
                                                })
                                              }
                                              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                                            />
                                          </label>

                                          <div className="mt-2 grid gap-2 sm:grid-cols-2">
                                            <label className="text-[11px] text-slate-400">
                                              Sample value
                                              <input
                                                type="text"
                                                value={variable.sample_value}
                                                onChange={(event) =>
                                                  updateDraftStepVariable(draft.draft_id, idx, variableIdx, {
                                                    sample_value: event.target.value,
                                                  })
                                                }
                                                className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                                              />
                                            </label>
                                            <label className="text-[11px] text-slate-400">
                                              Future value source
                                              <select
                                                value={variable.input_source}
                                                onChange={(event) =>
                                                  updateDraftStepVariable(draft.draft_id, idx, variableIdx, {
                                                    input_source: event.target.value,
                                                  })
                                                }
                                                className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                                              >
                                                <option value="ask_user">Ask user at runtime</option>
                                                <option value="client_record">Pull from client record</option>
                                                <option value="fixed_default">Use fixed default</option>
                                                <option value="derive_previous_step">Derive from previous step</option>
                                              </select>
                                            </label>
                                          </div>

                                          <label className="mt-2 block text-[11px] text-slate-400">
                                            Source detail (optional)
                                            <input
                                              type="text"
                                              value={variable.source_detail}
                                              onChange={(event) =>
                                                updateDraftStepVariable(draft.draft_id, idx, variableIdx, {
                                                  source_detail: event.target.value,
                                                })
                                              }
                                              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                                            />
                                          </label>

                                          <div className="mt-2 flex gap-4 text-[11px] text-slate-300">
                                            <label className="flex items-center gap-1">
                                              <input
                                                type="checkbox"
                                                checked={variable.is_variable}
                                                onChange={(event) =>
                                                  updateDraftStepVariable(draft.draft_id, idx, variableIdx, {
                                                    is_variable: event.target.checked,
                                                  })
                                                }
                                              />
                                              Variable each run
                                            </label>
                                            <label className="flex items-center gap-1">
                                              <input
                                                type="checkbox"
                                                checked={variable.required_input}
                                                onChange={(event) =>
                                                  updateDraftStepVariable(draft.draft_id, idx, variableIdx, {
                                                    required_input: event.target.checked,
                                                  })
                                                }
                                              />
                                              Required workflow input
                                            </label>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))}

                              <div className="flex justify-end">
                                <button
                                  type="button"
                                  onClick={() => void saveDraftStructure(draft)}
                                  disabled={learningBusyKey !== null}
                                  className={BUTTON_PRIMARY}
                                >
                                  {learningBusyKey === `save-structure-${draft.draft_id}` ? "Saving..." : "Save Structured Draft"}
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => void deleteDraft(draft.draft_id, draft.workflow_name)}
                          disabled={learningBusyKey !== null}
                          className={BUTTON_DANGER}
                        >
                          {learningBusyKey === `delete-${draft.draft_id}` ? "Deleting..." : "Delete"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void updateDraftStatus(draft.draft_id, "in_review")}
                          disabled={learningBusyKey !== null}
                          className={BUTTON_SECONDARY}
                        >
                          In Review
                        </button>
                        <button
                          type="button"
                          onClick={() => void updateDraftStatus(draft.draft_id, "approved")}
                          disabled={learningBusyKey !== null}
                          className={BUTTON_SECONDARY}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => startTeachingSession(draft.draft_id)}
                          disabled={learningBusyKey !== null}
                          className={teachingSessionDraftId === draft.draft_id ? `${BUTTON_ACCENT_GHOST} border-amber-400/40 bg-amber-500/10 text-amber-200 hover:bg-amber-500/20` : BUTTON_ACCENT_GHOST}
                        >
                          {teachingSessionDraftId === draft.draft_id ? "● Teaching Active" : "Teach Steps"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void testDraftGuided(draft.draft_id)}
                          disabled={learningBusyKey !== null}
                          className={BUTTON_ACCENT_GHOST}
                        >
                          {learningBusyKey === `test-${draft.draft_id}` ? "Testing..." : "Test Mode"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void publishDraft(draft.draft_id)}
                          disabled={learningBusyKey !== null || draft.review_status !== "approved"}
                          className={BUTTON_PRIMARY}
                        >
                          {learningBusyKey === `publish-${draft.draft_id}` ? "Publishing..." : "Publish"}
                        </button>
                      </div>
                    </article>
                  ))
                )}
              </div>
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

      {/* Teaching Mode Floating Overlay */}
      {teachingSessionDraftId !== null && (
        <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-2">
          {teachingOverlayOpen && (
            <div className="w-80 overflow-hidden rounded-2xl border border-slate-700/80 bg-slate-950/95 shadow-2xl shadow-black/70 backdrop-blur-sm">
              {/* Header */}
              <div className={`flex items-center justify-between border-b border-slate-800/80 px-4 py-3 ${teachingStatusRing}`}>
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 flex-shrink-0 rounded-full ${teachingStatusDot}`} />
                  <span className="text-xs font-semibold text-slate-100">Teaching Mode Active</span>
                </div>
                <button
                  type="button"
                  onClick={() => setTeachingOverlayOpen(false)}
                  className="ml-2 text-slate-500 transition hover:text-slate-200"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {/* Workflow info */}
              <div className="border-b border-slate-800/60 px-4 py-3">
                <p className="truncate text-sm font-semibold text-slate-100">
                  {teachingActiveDraft?.workflow_name ?? "—"}
                </p>
                <div className="mt-1.5 flex items-center gap-3 text-xs text-slate-400">
                  <span>
                    Status:{" "}
                    <span
                      className={
                        teachingStatus === "step_captured"
                          ? "text-emerald-300"
                          : teachingStatus === "waiting_clarification"
                            ? "text-cyan-300"
                            : teachingStatus === "paused"
                              ? "text-slate-400"
                              : "text-amber-300"
                      }
                    >
                      {teachingStatusLabel}
                    </span>
                  </span>
                  <span className="text-slate-600">·</span>
                  <span>
                    Steps: <span className="text-slate-200">{teachingActiveDraft?.steps?.length ?? 0}</span>
                  </span>
                </div>
              </div>

              {/* Last captured strip */}
              {(teachingActiveDraft?.steps?.length ?? 0) > 0 && (() => {
                const lastStep = teachingActiveDraft!.steps![teachingActiveDraft!.steps!.length - 1];
                return (
                  <div className="border-b border-slate-800/60 bg-slate-900/40 px-4 py-2">
                    <p className="text-[10px] uppercase tracking-wider text-slate-500">Last Captured</p>
                    <p className="mt-0.5 truncate text-xs text-slate-200">{lastStep.step_name}</p>
                    <p className="truncate text-[10px] text-slate-500">
                      {lastStep.action}
                      {" · "}
                      {lastStep.selector || lastStep.url || "—"}
                    </p>
                  </div>
                );
              })()}

              {/* Observation Browser launcher */}
              <div className="border-b border-slate-800/60 px-4 py-3">
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Observation Browser
                  </p>
                  {teachingLaunchStatus === "running" && (
                    <span className="rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-300">
                      Running · PID {teachingLaunchPid}
                    </span>
                  )}
                  {teachingLaunchStatus === "error" && (
                    <span className="rounded-full border border-rose-400/30 bg-rose-500/10 px-2 py-0.5 text-[10px] text-rose-300">
                      Launch failed
                    </span>
                  )}
                </div>
                <input
                  type="text"
                  value={teachingStartUrl}
                  onChange={(e) => setTeachingStartUrl(e.target.value)}
                  placeholder="https://start-url.com (optional)"
                  className="w-full rounded-lg border border-slate-700 bg-slate-900/80 px-2.5 py-1.5 text-xs text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-1 focus:ring-cyan-500/30"
                />
                <button
                  type="button"
                  onClick={() => void launchTeachBrowser()}
                  disabled={teachingLaunchStatus === "launching"}
                  className="mt-2 w-full rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-200 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {teachingLaunchStatus === "launching" ? "Launching\u2026" : "Launch Observation Browser"}
                </button>
                <p className="mt-1.5 text-[10px] text-slate-500">
                  Opens a Playwright browser that records clicks, text, and navigation as draft steps.
                </p>
              </div>

              {/* Q&A body */}
              <div className="px-4 py-3">
                {teachingCurrentQuestion && !teachingCurrentQuestion.teaching_complete ? (
                  <div>
                    <div className="mb-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-cyan-400">
                        Step {teachingCurrentQuestion.step_order}: {teachingCurrentQuestion.step_name}
                      </p>
                      {teachingCurrentQuestion.steps_remaining > 0 && (
                        <p className="mt-0.5 text-[10px] text-slate-500">
                          {teachingCurrentQuestion.steps_remaining} step
                          {teachingCurrentQuestion.steps_remaining !== 1 ? "s" : ""} remaining after this
                        </p>
                      )}
                    </div>
                    <div className="max-h-56 space-y-3 overflow-y-auto pr-1">
                      {teachingCurrentQuestion.questions.map((q, qi) => (
                        <div key={`tq-${qi}`}>
                          <p className="text-[11px] leading-relaxed text-slate-300">{q.question}</p>
                          {q.current_value && !teachingAnswers[q.field] && (
                            <p className="mt-0.5 text-[10px] italic text-slate-500">Current: {q.current_value}</p>
                          )}
                          {q.options.length > 0 ? (
                            <div className="mt-1.5 flex flex-wrap gap-1.5">
                              {q.options.map((opt) => (
                                <button
                                  key={opt}
                                  type="button"
                                  onClick={() => setTeachingAnswers((prev) => ({ ...prev, [q.field]: opt }))}
                                  className={`rounded-full px-2.5 py-1 text-[11px] font-medium transition ${
                                    (teachingAnswers[q.field] ?? q.current_value) === opt
                                      ? "bg-cyan-500 text-slate-950 shadow shadow-cyan-500/30"
                                      : "border border-slate-700 bg-slate-900 text-slate-300 hover:border-cyan-400/50 hover:text-cyan-200"
                                  }`}
                                >
                                  {opt}
                                </button>
                              ))}
                            </div>
                          ) : (
                            <input
                              type="text"
                              value={teachingAnswers[q.field] ?? q.current_value ?? ""}
                              onChange={(e) =>
                                setTeachingAnswers((prev) => ({ ...prev, [q.field]: e.target.value }))
                              }
                              className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-900/80 px-2.5 py-1.5 text-xs text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-1 focus:ring-cyan-500/30"
                            />
                          )}
                        </div>
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={() => void submitTeachingAnswers()}
                      disabled={learningBusyKey !== null}
                      className="mt-3 w-full rounded-lg bg-cyan-500 px-3 py-2 text-xs font-semibold text-slate-950 shadow shadow-cyan-500/20 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {learningBusyKey?.startsWith("teach-submit") ? "Saving\u2026" : "Submit Answers \u2192"}
                    </button>
                  </div>
                ) : teachingCurrentQuestion?.teaching_complete ? (
                  <div className="py-3 text-center">
                    <p className="text-xl">✓</p>
                    <p className="mt-1 text-sm font-semibold text-emerald-300">All steps taught</p>
                    <p className="mt-1 text-xs text-slate-400">Review the draft and publish when ready.</p>
                  </div>
                ) : (
                  <div className="py-1">
                    <p className="text-xs leading-relaxed text-slate-400">
                      {teachingActiveDraft?.learning_path === "demonstration"
                        ? "Demonstration mode — steps are captured as you perform actions in the browser."
                        : "Start the teaching loop to answer enrichment questions for each step."}
                    </p>
                    <button
                      type="button"
                      onClick={() => void loadTeachingQuestion(teachingSessionDraftId)}
                      disabled={learningBusyKey !== null || (teachingActiveDraft?.steps?.length ?? 0) === 0}
                      className="mt-3 w-full rounded-lg bg-cyan-500 px-3 py-2 text-xs font-semibold text-slate-950 shadow shadow-cyan-500/20 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {(teachingActiveDraft?.steps?.length ?? 0) === 0
                        ? "No steps — use Plain English path first"
                        : learningBusyKey?.startsWith("teach-load")
                          ? "Loading\u2026"
                          : "Start Teaching Loop"}
                    </button>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="flex flex-wrap gap-2 rounded-b-2xl border-t border-slate-800/60 px-4 py-3">
                <button
                  type="button"
                  onClick={pauseResumeTeaching}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-[11px] text-slate-300 transition hover:border-amber-400/50 hover:text-amber-300"
                >
                  {teachingStatus === "paused" ? "Resume" : "Pause"}
                </button>
                <button
                  type="button"
                  onClick={() => void finishTeachingSession()}
                  className="rounded-lg border border-rose-400/20 bg-rose-500/5 px-3 py-1.5 text-[11px] text-rose-300 transition hover:bg-rose-500/15"
                >
                  Finish Teaching
                </button>
              </div>
            </div>
          )}

          {/* Floating pill badge */}
          <button
            type="button"
            onClick={() => setTeachingOverlayOpen((prev) => !prev)}
            className={`flex items-center gap-2.5 rounded-full border px-4 py-2.5 shadow-lg shadow-black/50 backdrop-blur-sm transition hover:scale-[1.03] active:scale-100 ${teachingStatusRing}`}
          >
            <span className={`h-2 w-2 flex-shrink-0 rounded-full ${teachingStatusDot}`} />
            <span className="whitespace-nowrap text-xs font-semibold text-slate-100">Teaching Mode</span>
            {teachingActiveDraft && (
              <span className="max-w-[7rem] truncate text-xs text-slate-400">
                {teachingActiveDraft.workflow_name}
              </span>
            )}
            <span className="rounded-full bg-slate-800/80 px-1.5 py-0.5 text-[10px] font-medium text-slate-300">
              {teachingActiveDraft?.steps?.length ?? 0}
            </span>
            <svg
              className={`h-3 w-3 flex-shrink-0 text-slate-500 transition-transform ${teachingOverlayOpen ? "rotate-180" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      )}
    </main>
  );
}
