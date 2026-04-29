"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import MobileNav, { type MobileView } from "./components/MobileNav";
import MobileDashboard from "./components/MobileDashboard";
import AlertsPanel, { type AlertItem, type AlertKind, type HelpTask } from "./components/AlertsPanel";
import BillVoiceControls from "./components/BillVoiceControls";
import RecoveryPanel from "./components/RecoveryPanel";
import RecoveryAnalyticsPanel from "./components/RecoveryAnalyticsPanel";
import { BillHeader } from "./components/BillHeader";
import { CommandCenterCard } from "./components/CommandCenterCard";
import { WorkersPanel } from "./components/WorkersPanel";
import { RecentActivityPanel } from "./components/RecentActivityPanel";
import { ActiveTasksPanel } from "./components/ActiveTasksPanel";
import { AdvancedToolsTabs } from "./components/AdvancedToolsTabs";
import { SystemHealthFooter } from "./components/SystemHealthFooter";
import { useBillMic } from "./hooks/useBillMic";
import { useBillVoice } from "./hooks/useBillVoice";
import { useVoice } from "./hooks/useVoice";

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
  update_status?: string | null;
  update_target_version?: string | null;
  update_error?: string | null;
};

type WorkerRelease = {
  id: string;
  version: string;
  upload_time: string;
  release_notes?: string | null;
  package_filename: string;
  package_sha256?: string | null;
  is_active: boolean;
  channel: string;
};

type DeployWorkerStatus = {
  machine_uuid: string;
  machine_name?: string | null;
  worker_version?: string | null;
  update_status?: string | null;
  update_target_version?: string | null;
  update_error?: string | null;
  update_started_at?: string | null;
};

type WorkerDeployStatus = {
  active_release_version?: string | null;
  workers: DeployWorkerStatus[];
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

type SpeechRecognitionResultLike = {
  isFinal: boolean;
  0: { transcript: string };
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

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
  speak_response?: boolean;
  voice_text?: string | null;
  suggested_emotion?: string | null;
  suggested_style_profile?: string | null;
  voice_event_type?: string | null;
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

type HelpTasksResponse = {
  count: number;
  tasks: HelpTask[];
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

type TeachOverlayPrompt = {
  prompt_id: string;
  question: string;
  category?: string;
  purpose?: string;
  expected_answer_shape?: string;
  question_type?: string;
  trigger_type?: string;
  parent_question_id?: string | null;
  follow_up_count?: number;
  max_follow_ups?: number;
  clarity_score?: number | null;
  accepted?: boolean;
  learned_fact?: string | null;
  structured_output?: Record<string, unknown> | null;
  system_context?: Record<string, unknown>;
};

type TeachOverlaySettings = {
  auto_speak_questions?: boolean;
  max_follow_ups_per_question?: number;
  min_seconds_between_questions?: number;
  do_not_ask_while_user_typing?: boolean;
  question_frequency_mode?: "training" | "assisted" | "production";
  pause_until?: number | null;
};

type TeachAnswerSubmitResponse = {
  status?: string;
  conversation_state?: string;
  clarity_score?: number | null;
  missing_information?: string[];
  accepted?: boolean;
  suggested_follow_up_question?: string | null;
  learned_rule_preview?: Record<string, unknown> | null;
};

type TeachOverlayQuestionResponse = {
  session_id: string;
  workflow_id?: string;
  tenant_id?: string;
  question?: TeachOverlayPrompt | null;
  step_order: number;
  teaching_complete: boolean;
  observation_questions_paused: boolean;
  observation_skip_all_questions: boolean;
  steps_recorded?: number;
  conversation_state?: string;
  settings?: TeachOverlaySettings;
};

const NEXT_PUBLIC_API_BASE_DEFAULT = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com";
const COMMAND_CENTER_VOICE_PREF_KEY = "bill.command-center.voice.enabled";

const getConfiguredApiBase = (): string => {
  const configured = (process.env.NEXT_PUBLIC_API_BASE ?? "").trim();
  return configured ? configured.replace(/\/$/, "") : NEXT_PUBLIC_API_BASE_DEFAULT;
};

const getApiBase = (): string => {
  // When running in a browser over HTTPS, use the Next.js API proxy to avoid
  // mixed-content blocking (HTTPS page -> HTTP backend).
  if (typeof window !== "undefined" && window.location.protocol === "https:") {
    return "/api/proxy";
  }
  return getConfiguredApiBase();
};

// Worker payloads must always use the real backend URL (never /api/proxy).
const getWorkerApiBase = (): string => getConfiguredApiBase();

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

const updateStatusClasses = (status?: string | null): string => {
  const s = (status ?? "").toLowerCase();
  if (s === "updated") return "bg-emerald-500/15 text-emerald-200 border border-emerald-400/30";
  if (s === "failed") return "bg-rose-500/15 text-rose-200 border border-rose-400/30";
  if (s === "downloading" || s === "installing") return "bg-sky-500/15 text-sky-200 border border-sky-400/30";
  if (s === "pending" || s === "restarting") return "bg-amber-500/15 text-amber-200 border border-amber-400/30";
  return "bg-slate-700/60 text-slate-400 border border-slate-600/50";
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

const hashText = (text: string): string => {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash << 5) - hash + text.charCodeAt(i);
    hash |= 0;
  }
  return String(hash);
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
  const [teachingOverlayQuestion, setTeachingOverlayQuestion] = useState<TeachOverlayQuestionResponse | null>(null);
  const [teachingOverlayAnswer, setTeachingOverlayAnswer] = useState("");
  const [teachingOverlayTaskId, setTeachingOverlayTaskId] = useState<string | null>(null);
  const [teachingOverlayBusyKey, setTeachingOverlayBusyKey] = useState<string | null>(null);
  const [teachingOverlayError, setTeachingOverlayError] = useState<string | null>(null);
  const [teachingOverlayConversationState, setTeachingOverlayConversationState] = useState<string>("idle");
  const [teachingOverlayClarityScore, setTeachingOverlayClarityScore] = useState<number | null>(null);
  const [teachingOverlayMissingInfo, setTeachingOverlayMissingInfo] = useState<string[]>([]);
  const [teachingOverlayAccepted, setTeachingOverlayAccepted] = useState<boolean | null>(null);
  const [teachingOverlayFollowUpText, setTeachingOverlayFollowUpText] = useState<string | null>(null);
  const [teachingOverlayLearnedRulePreview, setTeachingOverlayLearnedRulePreview] = useState<Record<string, unknown> | null>(null);
  const [teachingOverlayAutoSpeakQuestions, setTeachingOverlayAutoSpeakQuestions] = useState<boolean>(true);
  const [teachingOverlayFrequencyMode, setTeachingOverlayFrequencyMode] = useState<"training" | "assisted" | "production">("assisted");
  const [teachingOverlayLastTypingAt, setTeachingOverlayLastTypingAt] = useState<number>(0);
  const [teachingOverlayDictating, setTeachingOverlayDictating] = useState(false);
  const [teachingOverlaySpeechSupported, setTeachingOverlaySpeechSupported] = useState(false);
  const [teachingStartUrl, setTeachingStartUrl] = useState<string>("");
  const [teachingTargetWorkerUuid, setTeachingTargetWorkerUuid] = useState<string>("");
  const [teachingLaunchStatus, setTeachingLaunchStatus] = useState<null | "launching" | "running" | "error">(null);
  const [teachingLaunchPid, setTeachingLaunchPid] = useState<number | null>(null);
  const prevTeachingStepCountRef = useRef<number>(0);
  // Worker rename state
  const [renamingMachineUuid, setRenamingMachineUuid] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState<string>("");
  const [chatHistory, setChatHistory] = useState<ChatEntry[]>([
    {
      role: "assistant",
      message:
        "I am Bill Core Orchestrator. Ask things like: 'Which worker is free?', 'What failed last?', or 'Run Marketplace workflow on Worker A'.",
    },
  ]);

  // Worker Update Management state
  const [workerReleases, setWorkerReleases] = useState<WorkerRelease[]>([]);
  const [workerDeployStatus, setWorkerDeployStatus] = useState<WorkerDeployStatus | null>(null);
  const [releaseUploadVersion, setReleaseUploadVersion] = useState("");
  const [releaseUploadNotes, setReleaseUploadNotes] = useState("");
  const [releaseUploadChannel, setReleaseUploadChannel] = useState("optional");
  const [releaseUploadFile, setReleaseUploadFile] = useState<File | null>(null);
  const [releaseUploadBusy, setReleaseUploadBusy] = useState(false);
  const [releaseBusyKey, setReleaseBusyKey] = useState<string | null>(null);
  const [releasesFeedback, setReleasesFeedback] = useState<ActionFeedback | null>(null);
  const [deployBusy, setDeployBusy] = useState(false);
  const [deployForce, setDeployForce] = useState(false);
  const [deployIdleOnly, setDeployIdleOnly] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  // ── Mobile / Phase 1-5 state ────────────────────────────────────────────────
  const [mobileView, setMobileView] = useState<MobileView>("status");
  const [humanHelpTasks, setHumanHelpTasks] = useState<HelpTask[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [resolveBusyKey, setResolveBusyKey] = useState<string | null>(null);
  const [notificationPermission, setNotificationPermission] = useState<
    NotificationPermission | "unsupported"
  >("unsupported");

  // Refs for alert diffing (previous poll state)
  const prevTasksRef = useRef<Task[]>([]);
  const prevMachinesRef = useRef<Machine[]>([]);

  const selectedMachine = machines.find((machine) => machine.machine_uuid === targetMachineUuid) ?? null;

  const logTeachOverlay = useCallback((message: string, details?: Record<string, unknown>) => {
    console.info("[teach-overlay]", message, details ?? {});
  }, []);

  // ── Voice (Phase 4) ──────────────────────────────────────────────────────────
  const { isSupported: voiceSupported, isListening, isSpeaking, ttsEnabled, setTtsEnabled, startListening, stopListening, speak } = useVoice({
    onTranscript: (text) => {
      setChatInput(text);
    },
  });
  const billVoice = useBillVoice(getApiBase());
  const commandMic = useBillMic();
  const [commandVoiceEnabled, setCommandVoiceEnabled] = useState<boolean>(true);
  const [commandVoiceEmotion, setCommandVoiceEmotion] = useState<string>("helpful");
  const [commandVoiceStyleProfile, setCommandVoiceStyleProfile] = useState<string>("default");
  const [lastCommandResponseText, setLastCommandResponseText] = useState<string>("");
  const lastSpokenHashRef = useRef<string>("");
  const lastSpokenAtRef = useRef<number>(0);
  const lastTeachOverlaySpokenPromptRef = useRef<string>("");
  const lastVoiceEventRef = useRef<{ eventType: string; at: number }>({ eventType: "", at: 0 });
  const teachRecognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const teachingOverlayVoiceEnabled = Boolean(
    commandVoiceEnabled && billVoice.config?.voice_enabled && billVoice.config?.configured,
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const speechWindow = window as Window & {
      SpeechRecognition?: SpeechRecognitionCtor;
      webkitSpeechRecognition?: SpeechRecognitionCtor;
    };
    setTeachingOverlaySpeechSupported(
      Boolean(window.speechSynthesis) && Boolean(speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition),
    );
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = window.localStorage.getItem(COMMAND_CENTER_VOICE_PREF_KEY);
    if (raw === "0") {
      setCommandVoiceEnabled(false);
      setTtsEnabled(false);
    } else if (raw === "1") {
      setCommandVoiceEnabled(true);
      setTtsEnabled(true);
    }
  }, [setTtsEnabled]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(COMMAND_CENTER_VOICE_PREF_KEY, commandVoiceEnabled ? "1" : "0");
    setTtsEnabled(commandVoiceEnabled);
  }, [commandVoiceEnabled, setTtsEnabled]);

  const queueBillEventSpeech = useCallback(
    (eventType: string, options?: { taskId?: string; workflowName?: string; context?: Record<string, unknown>; overrideText?: string }) => {
      if (!commandVoiceEnabled) return;
      if (!billVoice.config?.voice_enabled || !billVoice.config?.configured) return;
      void billVoice.speakEvent({
        event_type: eventType,
        task_id: options?.taskId,
        workflow_name: options?.workflowName,
        context: options?.context,
        override_text: options?.overrideText,
      });
      lastVoiceEventRef.current = { eventType, at: Date.now() };
    },
    [billVoice, commandVoiceEnabled],
  );

  // Init notification permission state on mount
  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window) {
      setNotificationPermission(Notification.permission);
    }
  }, []);

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
    const helpUrl = `${apiBase}/api/tasks/needs-human-help`;

    const [healthResult, machinesResult, tasksResult, helpResult] = await Promise.allSettled([
      fetchJson<HealthResponse>(healthUrl),
      fetchJson<Machine[]>(machinesUrl),
      fetchJson<Task[]>(tasksUrl),
      fetchJson<HelpTasksResponse>(helpUrl),
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

      // ── Alert diffing: detect new failures, recoveries, completions ──────────
      const prev = prevTasksRef.current;
      const prevById = new Map(prev.map((t) => [t.id, t]));
      const newAlerts: AlertItem[] = [];

      for (const task of nextTasks) {
        const prevTask = prevById.get(task.id);
        const prevStatus = (prevTask?.status ?? "").toLowerCase();
        const currStatus = (task.status ?? "").toLowerCase();

        if (prevTask && prevStatus !== currStatus) {
          const name = (task.payload?.task_type as string | undefined) ?? "Task";
          const short = (task.id ?? "").slice(0, 8);

          if (currStatus === "failed") {
            newAlerts.push({
              id: `alert-fail-${task.id}-${Date.now()}`,
              kind: "task_failed" as AlertKind,
              title: `${name} failed`,
              detail: task.error ?? `Task ${short} reported a failure.`,
              timestamp: new Date().toISOString(),
              taskId: task.id,
              taskPayload: task.payload as Record<string, unknown> | undefined,
            });
            _sendBrowserNotification(`Task Failed: ${name}`, task.error ?? short);
            queueBillEventSpeech("recovery_stuck", {
              taskId: task.id,
              workflowName: String(task.payload?.workflow_name ?? task.payload?.task_type ?? ""),
              context: {
                event_type: "task_failed",
                error: task.error ?? "",
              },
            });
          } else if (currStatus === "needs_human_help") {
            newAlerts.push({
              id: `alert-help-${task.id}-${Date.now()}`,
              kind: "needs_human" as AlertKind,
              title: `${name} needs your help`,
              detail: "All automated recovery exhausted. Human action required.",
              timestamp: new Date().toISOString(),
              taskId: task.id,
              taskPayload: task.payload as Record<string, unknown> | undefined,
            });
            _sendBrowserNotification(`Needs Attention: ${name}`, "Human intervention required.");
            queueBillEventSpeech("suggested_fix_available", {
              taskId: task.id,
              workflowName: String(task.payload?.workflow_name ?? task.payload?.task_type ?? ""),
              context: {
                event_type: "needs_human_help",
              },
            });
          } else if (currStatus === "recovering" && prevStatus !== "recovering") {
            newAlerts.push({
              id: `alert-recover-${task.id}-${Date.now()}`,
              kind: "recovering" as AlertKind,
              title: `${name} is recovering`,
              detail: "Timeout recovery in progress.",
              timestamp: new Date().toISOString(),
              taskId: task.id,
              taskPayload: task.payload as Record<string, unknown> | undefined,
            });
            queueBillEventSpeech("warning_risk", {
              taskId: task.id,
              workflowName: String(task.payload?.workflow_name ?? task.payload?.task_type ?? ""),
              context: {
                event_type: "recovering",
              },
            });
          } else if (currStatus === "completed" && prevStatus !== "completed") {
            newAlerts.push({
              id: `alert-done-${task.id}-${Date.now()}`,
              kind: "task_completed" as AlertKind,
              title: `${name} completed`,
              detail: `Task ${short} finished successfully.`,
              timestamp: new Date().toISOString(),
              taskId: task.id,
            });
            queueBillEventSpeech("workflow_completed", {
              taskId: task.id,
              workflowName: String(task.payload?.workflow_name ?? task.payload?.task_type ?? ""),
              context: {
                event_type: "task_completed",
              },
            });
          }
        }
      }

      if (newAlerts.length > 0) {
        setAlerts((prev) => [...newAlerts, ...prev].slice(0, 50));
      }
      prevTasksRef.current = nextTasks;
    } else {
      console.error(`[dashboard] Tasks fetch failed for ${tasksUrl}`, tasksResult.reason);
      nextErrors.tasks = `Tasks fetch failed: ${String(tasksResult.reason)}`;
    }

    // ── Alert diffing for workers going offline ─────────────────────────────
    if (machinesResult.status === "fulfilled") {
      const nextMachines = Array.isArray(machinesResult.value) ? machinesResult.value : [];
      const prevMachines = prevMachinesRef.current;
      const prevByUuid = new Map(prevMachines.map((m) => [m.machine_uuid, m]));

      for (const machine of nextMachines) {
        const prev = prevByUuid.get(machine.machine_uuid);
        if (prev?.online && !machine.online) {
          const name = machine.machine_name ?? machine.worker_name ?? machine.machine_uuid ?? "Worker";
          setAlerts((current) => [
            {
              id: `alert-offline-${machine.machine_uuid}-${Date.now()}`,
              kind: "worker_offline" as AlertKind,
              title: `${name} went offline`,
              detail: `Last status: ${prev.status ?? "unknown"}`,
              timestamp: new Date().toISOString(),
              workerName: name,
            },
            ...current,
          ].slice(0, 50));
          _sendBrowserNotification(`Worker Offline: ${name}`, "The worker is no longer reachable.");
        }
      }
      prevMachinesRef.current = nextMachines;
    }

    // ── Human help tasks ────────────────────────────────────────────────────
    if (helpResult.status === "fulfilled" && helpResult.value) {
      setHumanHelpTasks((helpResult.value as HelpTasksResponse).tasks ?? []);
    }

    setErrors(nextErrors);
    setLastUpdated(new Date());
  };

  const loadBrainPanels = async () => {
    const apiBase = getApiBase();
    if (!apiBase) {
      return;
    }

    const workflowsUrl = `${apiBase}/api/workflows`;
    const auditUrl = `${apiBase}/api/brain/audit?limit=20`;
    const draftsUrl = `${apiBase}/api/brain/workflow-learning/drafts?limit=100`;
    const releasesUrl = `${apiBase}/api/worker/releases`;
    const deployStatusUrl = `${apiBase}/api/worker/deploy/status`;
    const [workflowsResult, auditResult, draftsResult, releasesResult, deployStatusResult] = await Promise.allSettled([
      fetchJson<WorkflowRecord[]>(workflowsUrl),
      fetchJson<BrainAuditEntry[]>(auditUrl),
      fetchJson<WorkflowLearningDraft[]>(draftsUrl),
      fetchJson<WorkerRelease[]>(releasesUrl),
      fetchJson<WorkerDeployStatus>(deployStatusUrl),
    ]);

    setErrors((current) => {
      const next = { ...current };

      if (workflowsResult.status === "fulfilled") {
        const nextWorkflows = Array.isArray(workflowsResult.value) ? workflowsResult.value : [];
        setWorkflows(nextWorkflows);
        if (nextWorkflows.length > 0) {
          setHelperWorkflow((prev) => prev || nextWorkflows[0].workflow_name);
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

      if (releasesResult.status === "fulfilled") {
        setWorkerReleases(Array.isArray(releasesResult.value) ? releasesResult.value : []);
      }

      if (deployStatusResult.status === "fulfilled" && deployStatusResult.value) {
        setWorkerDeployStatus(deployStatusResult.value as WorkerDeployStatus);
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

  // ── Worker Update Management handlers ──────────────────────────────────────

  const uploadRelease = async () => {
    if (!releaseUploadVersion.trim() || !releaseUploadFile) return;
    const apiBase = getApiBase();
    if (!apiBase) return;
    setReleaseUploadBusy(true);
    setReleasesFeedback(null);
    try {
      const form = new FormData();
      form.append("version", releaseUploadVersion.trim());
      form.append("release_notes", releaseUploadNotes);
      form.append("channel", releaseUploadChannel);
      form.append("package", releaseUploadFile);
      const res = await fetch(`${apiBase}/api/worker/releases`, { method: "POST", body: form });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Upload failed (${res.status}): ${text}`);
      }
      setReleaseUploadVersion("");
      setReleaseUploadNotes("");
      setReleaseUploadFile(null);
      setFeedback(setReleasesFeedback, "success", "Release uploaded successfully.");
      await loadBrainPanels();
    } catch (err) {
      setFeedback(setReleasesFeedback, "error", err instanceof Error ? err.message : "Upload failed");
    } finally {
      setReleaseUploadBusy(false);
    }
  };

  const activateRelease = async (releaseId: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setReleaseBusyKey(`activate-${releaseId}`);
    setReleasesFeedback(null);
    try {
      const res = await fetch(`${apiBase}/api/worker/releases/${releaseId}/activate`, { method: "POST" });
      if (!res.ok) throw new Error(`Activate failed (${res.status})`);
      setFeedback(setReleasesFeedback, "success", "Release activated.");
      await loadBrainPanels();
    } catch (err) {
      setFeedback(setReleasesFeedback, "error", err instanceof Error ? err.message : "Activate failed");
    } finally {
      setReleaseBusyKey(null);
    }
  };

  const deleteRelease = async (releaseId: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setReleaseBusyKey(`delete-${releaseId}`);
    setReleasesFeedback(null);
    try {
      const res = await fetch(`${apiBase}/api/worker/releases/${releaseId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`Delete failed (${res.status})`);
      setFeedback(setReleasesFeedback, "success", "Release deleted.");
      await loadBrainPanels();
    } catch (err) {
      setFeedback(setReleasesFeedback, "error", err instanceof Error ? err.message : "Delete failed");
    } finally {
      setReleaseBusyKey(null);
    }
  };

  const renameWorker = async (machineUuid: string, newName: string) => {
    const apiBase = getApiBase();
    if (!apiBase || !newName.trim()) return;
    try {
      await fetch(`${apiBase}/api/machines/${machineUuid}/name`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ machine_name: newName.trim() }),
      });
      setMachines((prev) =>
        prev.map((m) => (m.machine_uuid === machineUuid ? { ...m, machine_name: newName.trim() } : m))
      );
    } catch {
      // silent — next poll will restore correct name
    }
    setRenamingMachineUuid(null);
  };

  const deleteWorker = async (machineUuid: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    try {
      await fetch(`${apiBase}/api/machines/${machineUuid}`, { method: "DELETE" });
      setMachines((prev) => prev.filter((m) => m.machine_uuid !== machineUuid));
    } catch {
      // silent
    }
  };

  const deployToWorkers = async (machineUuids?: string[]) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setDeployBusy(true);
    setReleasesFeedback(null);
    try {
      const res = await fetch(`${apiBase}/api/worker/deploy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ machine_uuids: machineUuids ?? null, force: deployForce, idle_only: deployIdleOnly }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Deploy failed (${res.status}): ${text}`);
      }
      const result = (await res.json()) as { message?: string };
      setFeedback(setReleasesFeedback, "success", result.message ?? "Deploy queued.");
      await loadBrainPanels();
    } catch (err) {
      setFeedback(setReleasesFeedback, "error", err instanceof Error ? err.message : "Deploy failed");
    } finally {
      setDeployBusy(false);
    }
  };

  // ── End Worker Update Management handlers ──────────────────────────────────

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

  const runSelectedWorkflow = async (workflowName: string) => {
    if (!workflowName) return;
    setLoading(true);
    setActionError(null);
    try {
      const apiBase = getApiBase();
      if (!apiBase) throw new Error("NEXT_PUBLIC_API_BASE is not set");
      const slug = workflowName.toLowerCase().replace(/\s+/g, "_");
      const url = `${apiBase}/api/procedures/${slug}/run`;
      const requestBody: Record<string, unknown> = { mode: "interactive_visible", payload: {} };
      if (targetMachineUuid) requestBody.target_machine_uuid = targetMachineUuid;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      const data = (await res.json()) as TaskCreateResponse;
      setResponse(data);
      if (!res.ok) {
        setActionError(`Run '${workflowName}' failed: ${res.status} ${JSON.stringify(data)}`);
      } else {
        setTaskActionFeedback({ kind: "success", message: `Started '${workflowName}'`, timestamp: new Date().toLocaleTimeString() });
        await loadDashboardData();
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
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
        queueBillEventSpeech("workflow_started", {
          workflowName: "smart_sherpa_sync",
          context: { source: "runSmartSherpaSync" },
        });
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
      setLastCommandResponseText(lines.join(". "));

      const responseVoiceText = (body.voice_text ?? "").trim() || lines.join(". ");
      if (commandVoiceEnabled && body.speak_response !== false && responseVoiceText) {
        const responseId = [
          body.task?.id ?? "",
          body.selected_workflow ?? "",
          responseVoiceText,
        ].join("|");
        const responseHash = hashText(responseId);
        const now = Date.now();
        const isDuplicateReplay = responseHash === lastSpokenHashRef.current;
        const isDuplicateQuickReplay =
          responseHash === lastSpokenHashRef.current && now - lastSpokenAtRef.current < 8000;
        const eventJustSpokeSimilar =
          body.voice_event_type &&
          body.voice_event_type === lastVoiceEventRef.current.eventType &&
          now - lastVoiceEventRef.current.at < 5000;

        if (!isDuplicateReplay && !isDuplicateQuickReplay && !eventJustSpokeSimilar) {
          const spoken = await billVoice.speakText({
            text: responseVoiceText,
            emotion: body.suggested_emotion ?? commandVoiceEmotion,
            style_profile: body.suggested_style_profile ?? commandVoiceStyleProfile,
            task_id: body.task?.id,
            workflow_name: body.selected_workflow ?? undefined,
            context: {
              event_type: body.voice_event_type ?? "brain_response",
              recognized_intent: body.recognized_intent ?? "",
              command: command,
              suggested_next_action: body.suggested_next_action ?? "",
            },
          });

          if (spoken) {
            lastSpokenHashRef.current = responseHash;
            lastSpokenAtRef.current = now;
          } else {
            speak(responseVoiceText);
          }
        }
      }

      if (body.task?.id && body.selected_workflow) {
        queueBillEventSpeech("workflow_started", {
          taskId: body.task.id,
          workflowName: body.selected_workflow,
          context: { source: "brain_command" },
        });
      }

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

  // ── Browser notifications (Phase 2) ─────────────────────────────────────────
  const _sendBrowserNotification = useCallback((title: string, body: string) => {
    if (typeof window === "undefined") return;
    if (!("Notification" in window)) return;
    if (Notification.permission !== "granted") return;
    try {
      new Notification(title, { body, icon: "/icon-192.png" });
    } catch {
      // Ignore — some browsers restrict programmatic notifications
    }
  }, []);

  const requestNotificationPermission = useCallback(async () => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    const result = await Notification.requestPermission();
    setNotificationPermission(result);
  }, []);

  // ── Resolve needs_human_help task (Phase 2/3) ────────────────────────────────
  const resolveHumanHelpTask = async (taskId: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setResolveBusyKey(`resolve-${taskId}`);
    try {
      const res = await fetch(`${apiBase}/api/tasks/${taskId}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolution: "Resolved from mobile dashboard." }),
      });
      if (!res.ok) throw new Error(`Resolve failed (${res.status})`);
      await loadDashboardData();
    } catch (err) {
      setFeedback(
        setTaskActionFeedback,
        "error",
        `Resolve failed: ${err instanceof Error ? err.message : "Unknown error"}`,
      );
    } finally {
      setResolveBusyKey(null);
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

  const loadTeachOverlayQuestion = useCallback(
    async (draftId: string, options?: { silent?: boolean }) => {
      if (!draftId) {
        return;
      }
      if (!options?.silent) {
        setTeachingOverlayBusyKey(`overlay-load-${draftId}`);
      }
      try {
        const apiBase = getApiBase();
        if (!apiBase) {
          throw new Error("NEXT_PUBLIC_API_BASE is not set");
        }
        logTeachOverlay("next question requested", { session_id: draftId });
        const response = await fetch(`${apiBase}/api/teach-sessions/${draftId}/questions/next`);
        const body = (await response.json()) as TeachOverlayQuestionResponse | { detail?: string };
        if (!response.ok) {
          throw new Error((body as { detail?: string }).detail ?? `Overlay question fetch failed (${response.status})`);
        }
        const nextQuestion = body as TeachOverlayQuestionResponse;
        setTeachingOverlayQuestion(nextQuestion);
        setTeachingOverlayConversationState(nextQuestion.conversation_state ?? (nextQuestion.question ? "asking_question" : "idle"));
        if (typeof nextQuestion.settings?.auto_speak_questions === "boolean") {
          setTeachingOverlayAutoSpeakQuestions(Boolean(nextQuestion.settings.auto_speak_questions));
        }
        if (nextQuestion.settings?.question_frequency_mode && ["training", "assisted", "production"].includes(nextQuestion.settings.question_frequency_mode)) {
          setTeachingOverlayFrequencyMode(nextQuestion.settings.question_frequency_mode);
        }
        setTeachingOverlayAnswer((current) => (
          nextQuestion.question?.prompt_id === teachingOverlayQuestion?.question?.prompt_id ? current : ""
        ));
        setTeachingOverlayError(null);
        logTeachOverlay("overlay question loaded", {
          session_id: draftId,
          question_loaded: Boolean(nextQuestion.question),
          paused: nextQuestion.observation_questions_paused,
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown error";
        setTeachingOverlayError(message);
        logTeachOverlay("overlay question request failed", { session_id: draftId, error: message });
      } finally {
        if (!options?.silent) {
          setTeachingOverlayBusyKey(null);
        }
      }
    },
    [logTeachOverlay, teachingOverlayQuestion?.question?.prompt_id],
  );

  const updateTeachOverlaySettings = useCallback(
    async (sessionId: string, settingsPatch: Record<string, unknown>) => {
      if (!sessionId) return;
      const apiBase = getApiBase();
      if (!apiBase) return;
      try {
        const response = await fetch(`${apiBase}/api/teach-sessions/${sessionId}/settings`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(settingsPatch),
        });
        if (!response.ok) {
          const body = (await response.json()) as { detail?: string };
          throw new Error(body.detail ?? `Update settings failed (${response.status})`);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown error";
        setTeachingOverlayError(message);
      }
    },
    [],
  );

  const startTeachingSession = async (draftId: string) => {
    logTeachOverlay("teach mode started", { session_id: draftId, target_worker_uuid: teachingTargetWorkerUuid || null });
    setTeachingSessionDraftId(draftId);
    setTeachingOverlayOpen(true);
    setTeachingStatus("watching");
    setTeachingCurrentQuestion(null);
    setTeachingAnswers({});
    setTeachingOverlayQuestion(null);
    setTeachingOverlayAnswer("");
    setTeachingOverlayTaskId(null);
    setTeachingOverlayError(null);
    setTeachingOverlayConversationState("asking_question");
    setTeachingOverlayClarityScore(null);
    setTeachingOverlayMissingInfo([]);
    setTeachingOverlayAccepted(null);
    setTeachingOverlayFollowUpText(null);
    setTeachingOverlayLearnedRulePreview(null);
    setTeachingOverlayAutoSpeakQuestions(true);
    setTeachingOverlayFrequencyMode("assisted");
    setTeachingLaunchStatus(null);
    setTeachingLaunchPid(null);
    await updateTeachOverlaySettings(draftId, {
      auto_speak_questions: true,
      question_frequency_mode: "assisted",
      max_follow_ups_per_question: 2,
      min_seconds_between_questions: 20,
      do_not_ask_while_user_typing: true,
    });
    await loadTeachingQuestion(draftId);
    await loadTeachOverlayQuestion(draftId);
    await launchTeachBrowser(draftId);
  };

  const submitTeachOverlayAnswer = async (action: "answer" | "skip") => {
    if (!teachingSessionDraftId) {
      return;
    }
    const prompt = teachingOverlayQuestion?.question;
    if (!prompt) {
      await loadTeachOverlayQuestion(teachingSessionDraftId);
      return;
    }

    setTeachingOverlayBusyKey(`overlay-${action}-${teachingSessionDraftId}`);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }
      const endpoint = action === "answer"
        ? `${apiBase}/api/teach-sessions/${teachingSessionDraftId}/answers`
        : `${apiBase}/api/teach-sessions/${teachingSessionDraftId}/questions/skip`;
      const payload = {
        prompt_id: prompt.prompt_id,
        step_order: teachingOverlayQuestion?.step_order ?? 0,
        answer: teachingOverlayAnswer,
        response_mode: "text",
        question_type: prompt.question_type,
        trigger_type: prompt.trigger_type,
        question_frequency: "medium",
        system_context: prompt.system_context ?? {},
      };
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = (await response.json()) as TeachAnswerSubmitResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail ?? `Overlay ${action} failed (${response.status})`);
      }
      setTeachingOverlayConversationState(body.conversation_state ?? "waiting_for_answer");
      setTeachingOverlayClarityScore(typeof body.clarity_score === "number" ? body.clarity_score : null);
      setTeachingOverlayMissingInfo(Array.isArray(body.missing_information) ? body.missing_information : []);
      setTeachingOverlayAccepted(typeof body.accepted === "boolean" ? body.accepted : null);
      setTeachingOverlayFollowUpText(body.suggested_follow_up_question ?? null);
      setTeachingOverlayLearnedRulePreview((body.learned_rule_preview ?? null) as Record<string, unknown> | null);
      if (body.accepted === true && teachingOverlayAutoSpeakQuestions) {
        void billVoice.speakText({
          text: "Got it. I will remember that.",
          emotion: "helpful",
          style_profile: commandVoiceStyleProfile,
        });
      } else if (body.accepted === false && teachingOverlayAutoSpeakQuestions) {
        void billVoice.speakText({
          text: "I think I understand part of that, but I need one detail clarified.",
          emotion: "helpful",
          style_profile: commandVoiceStyleProfile,
        });
      }
      logTeachOverlay(action === "answer" ? "answer submitted" : "question skipped", {
        session_id: teachingSessionDraftId,
        task_id: teachingOverlayTaskId,
        prompt_id: prompt.prompt_id,
      });
      setTeachingOverlayAnswer("");
      setTeachingOverlayError(null);
      await loadTeachOverlayQuestion(teachingSessionDraftId, { silent: true });
      await loadBrainPanels();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setTeachingOverlayError(message);
      logTeachOverlay("answer submission failed", { session_id: teachingSessionDraftId, error: message });
    } finally {
      setTeachingOverlayBusyKey(null);
    }
  };

  const toggleTeachOverlayPause = async () => {
    if (!teachingSessionDraftId) {
      return;
    }
    const shouldResume = Boolean(teachingOverlayQuestion?.observation_questions_paused);
    setTeachingOverlayBusyKey(`overlay-pause-${teachingSessionDraftId}`);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }
      const response = await fetch(`${apiBase}/api/teach-sessions/${teachingSessionDraftId}/questions/pause`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume: shouldResume, question_frequency: "medium" }),
      });
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail ?? `Overlay pause toggle failed (${response.status})`);
      }
      logTeachOverlay(shouldResume ? "questions resumed" : "questions paused", {
        session_id: teachingSessionDraftId,
      });
      await loadTeachOverlayQuestion(teachingSessionDraftId, { silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setTeachingOverlayError(message);
      logTeachOverlay("pause toggle failed", { session_id: teachingSessionDraftId, error: message });
    } finally {
      setTeachingOverlayBusyKey(null);
    }
  };

  const speakTeachOverlayQuestion = useCallback(async () => {
    const text = teachingOverlayQuestion?.question?.question?.trim();
    if (!text) {
      return;
    }

    // Prefer Bill voice when configured; otherwise use browser TTS fallback.
    if (teachingOverlayVoiceEnabled) {
      const played = await billVoice.speakText({
        text,
        emotion: commandVoiceEmotion,
        style_profile: commandVoiceStyleProfile,
        task_id: teachingOverlayTaskId ?? undefined,
        context: {
          source: "teach_overlay_question",
          session_id: teachingSessionDraftId,
          prompt_id: teachingOverlayQuestion?.question?.prompt_id,
        },
      });
      if (played) {
        return;
      }
    }

    if (typeof window === "undefined" || !window.speechSynthesis) {
      setTeachingOverlayError("Voice playback is not supported in this browser.");
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.onstart = () => setTeachingOverlayError(null);
    utterance.onerror = () => setTeachingOverlayError("Browser voice playback failed.");
    window.speechSynthesis.speak(utterance);
  }, [
    billVoice,
    commandVoiceEmotion,
    commandVoiceStyleProfile,
    teachingOverlayQuestion,
    teachingOverlayTaskId,
    teachingOverlayVoiceEnabled,
    teachingSessionDraftId,
  ]);

  const toggleTeachOverlayDictation = useCallback(() => {
    if (typeof window === "undefined") {
      return;
    }

    if (teachingOverlayDictating) {
      teachRecognitionRef.current?.stop();
      setTeachingOverlayDictating(false);
      return;
    }

    const speechWindow = window as Window & {
      SpeechRecognition?: SpeechRecognitionCtor;
      webkitSpeechRecognition?: SpeechRecognitionCtor;
    };
    const RecognitionCtor = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;

    if (!RecognitionCtor) {
      setTeachingOverlayError("Speech-to-text is not supported in this browser.");
      return;
    }

    const recognition = new RecognitionCtor();
    teachRecognitionRef.current = recognition;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        transcript += event.results[i][0]?.transcript ?? "";
      }
      if (!transcript.trim()) {
        return;
      }
      setTeachingOverlayAnswer((current) => {
        const base = current.trimEnd();
        return base ? `${base} ${transcript.trim()}` : transcript.trim();
      });
      setTeachingOverlayError(null);
    };
    recognition.onerror = (event) => {
      setTeachingOverlayError(`Dictation failed${event?.error ? `: ${event.error}` : ""}`);
      setTeachingOverlayDictating(false);
    };
    recognition.onend = () => {
      setTeachingOverlayDictating(false);
    };
    recognition.start();
    setTeachingOverlayDictating(true);
    setTeachingOverlayError(null);
  }, [teachingOverlayDictating]);

  useEffect(() => {
    if (!teachingSessionDraftId && teachRecognitionRef.current) {
      teachRecognitionRef.current.stop();
      setTeachingOverlayDictating(false);
    }
  }, [teachingSessionDraftId]);

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
    setTeachingOverlayQuestion(null);
    setTeachingOverlayAnswer("");
    setTeachingOverlayTaskId(null);
    setTeachingOverlayError(null);
    setTeachingOverlayConversationState("idle");
    setTeachingOverlayClarityScore(null);
    setTeachingOverlayMissingInfo([]);
    setTeachingOverlayAccepted(null);
    setTeachingOverlayFollowUpText(null);
    setTeachingOverlayLearnedRulePreview(null);
    setTeachingStatus("watching");
    await loadBrainPanels();
  };

  const launchTeachBrowser = async (draftIdOverride?: string) => {
    const draftId = draftIdOverride ?? teachingSessionDraftId;
    if (!draftId) return;
    const apiBase = getApiBase();
    const workerApiBase = getWorkerApiBase();
    if (!apiBase) return;
    setTeachingLaunchStatus("launching");
    try {
      const res = await fetch(
        `${apiBase}/api/brain/workflow-learning/drafts/${draftId}/teach-session/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            start_url: teachingStartUrl.trim(),
            api_base: workerApiBase,
            target_machine_uuid: teachingTargetWorkerUuid.trim(),
          }),
        },
      );
      const data = (await res.json()) as { pid?: number; status?: string; detail?: string; task_id?: string };
      if (!res.ok) throw new Error(data.detail ?? `Launch failed (${res.status})`);
      setTeachingLaunchPid(data.pid ?? null);
      setTeachingOverlayTaskId(data.task_id ?? null);
      setTeachingLaunchStatus("running");
      logTeachOverlay("overlay should open", {
        session_id: draftId,
        task_id: data.task_id ?? null,
        launch_status: data.status ?? "running",
      });
    } catch (err) {
      setTeachingLaunchStatus("error");
      setFeedback(
        setLearningFeedback,
        "error",
        `Browser launch failed: ${err instanceof Error ? err.message : "Unknown error"}`,
      );
      logTeachOverlay("teach mode launch failed", {
        session_id: draftId,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  };

  // Faster poll (2 s) while a teach session is active
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!teachingSessionDraftId) return;
    const id = setInterval(() => { void loadBrainPanels(); }, 2000);
    return () => clearInterval(id);
  }, [teachingSessionDraftId]);

  useEffect(() => {
    if (!teachingSessionDraftId || !teachingOverlayOpen) {
      return;
    }
    logTeachOverlay("overlay component mounted", {
      session_id: teachingSessionDraftId,
      task_id: teachingOverlayTaskId,
    });
  }, [logTeachOverlay, teachingOverlayOpen, teachingOverlayTaskId, teachingSessionDraftId]);

  useEffect(() => {
    if (!teachingSessionDraftId) {
      return;
    }
    const id = setInterval(() => {
      void loadTeachOverlayQuestion(teachingSessionDraftId, { silent: true });
    }, 3000);
    return () => clearInterval(id);
  }, [loadTeachOverlayQuestion, teachingSessionDraftId]);

  useEffect(() => {
    const prompt = teachingOverlayQuestion?.question;
    if (!teachingOverlayOpen || !prompt || !teachingOverlayAutoSpeakQuestions) {
      return;
    }
    const promptId = String(prompt.prompt_id || "");
    if (!promptId) {
      return;
    }
    if (lastTeachOverlaySpokenPromptRef.current === promptId) {
      return;
    }
    const minSeconds = Number(teachingOverlayQuestion?.settings?.min_seconds_between_questions ?? 20);
    const now = Date.now();
    if (now - lastSpokenAtRef.current < minSeconds * 1000) {
      return;
    }
    const doNotAskWhileTyping = Boolean(teachingOverlayQuestion?.settings?.do_not_ask_while_user_typing ?? true);
    if (doNotAskWhileTyping && now - teachingOverlayLastTypingAt < 1800) {
      return;
    }
    void speakTeachOverlayQuestion().then(() => {
      lastTeachOverlaySpokenPromptRef.current = promptId;
      lastSpokenAtRef.current = Date.now();
    });
  }, [
    speakTeachOverlayQuestion,
    teachingOverlayAutoSpeakQuestions,
    teachingOverlayLastTypingAt,
    teachingOverlayOpen,
    teachingOverlayQuestion,
  ]);

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
    <main className="min-h-screen bg-[#070a11] text-slate-100">

      {/* ── Desktop Command Center (hidden on mobile) ─────────────────────── */}
      <div className="hidden lg:block">
        <div className="mx-auto max-w-[1600px] px-6 py-6">

          {/* Header: logo + metric bar */}
          <BillHeader
            workersOnline={onlineWorkers.length}
            activeTasks={activeTasks.length}
            needsAttention={humanHelpTasks.length}
            failedTasks={failedTasks.length}
            completed24h={successfulTasks.length}
          />

          {errors.config && (
            <div className="mb-4 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {errors.config}
            </div>
          )}

          {/* Main grid: left content + right workers panel */}
          <div className="grid gap-6 lg:grid-cols-[1fr_340px]">

            {/* Left column */}
            <div className="space-y-6">

              {/* Primary command card */}
              <CommandCenterCard
                chatInput={chatInput}
                setChatInput={setChatInput}
                chatLoading={chatLoading}
                onSubmit={() => void submitBrainCommand()}
                commandVoiceEnabled={commandVoiceEnabled}
                setCommandVoiceEnabled={setCommandVoiceEnabled}
                voiceSupported={voiceSupported}
                isListening={isListening}
                startListening={startListening}
                stopListening={stopListening}
                billVoice={billVoice}
                commandMic={commandMic}
                workflows={workflows}
                loading={loading}
                helperWorkflow={helperWorkflow}
                setHelperWorkflow={setHelperWorkflow}
                onRunWorkflow={(name) => void runSelectedWorkflow(name)}
                onQuickAction={(cmd) => { setChatInput(cmd); void submitBrainCommand(cmd); }}
              />

              {/* Recent Activity + Active Tasks row */}
              <div className="grid gap-6 md:grid-cols-2">
                <RecentActivityPanel alerts={alerts} />
                <ActiveTasksPanel
                  activeTasks={activeTasks}
                  allTasks={tasks}
                  taskActionBusyKey={taskActionBusyKey}
                  onCancel={(id) => void cancelTask(id)}
                  onRetry={(task) => void retryFailedTask(task)}
                />
              </div>

              {/* Advanced tools — tabbed */}
              <AdvancedToolsTabs
                apiBase={getApiBase()}
                billVoice={billVoice}
                auditEntries={auditEntries}
                onRefreshAudit={() => void loadBrainPanels()}
                auditError={errors.audit}
                learningPath={learningPath}
                setLearningPath={setLearningPath}
                learningWorkflowName={learningWorkflowName}
                setLearningWorkflowName={setLearningWorkflowName}
                learningGoal={learningGoal}
                setLearningGoal={setLearningGoal}
                learningSourceText={learningSourceText}
                setLearningSourceText={setLearningSourceText}
                learningBusyKey={learningBusyKey}
                learningFeedback={learningFeedback}
                workflowDrafts={workflowDrafts}
                expandedDraftId={expandedDraftId}
                setExpandedDraftId={setExpandedDraftId}
                onCreateDraft={() => void createWorkflowDraft()}
                onDeleteDraft={(id, name) => void deleteDraft(id, name)}
                onUpdateDraftStatus={(id, status) => void updateDraftStatus(id, status)}
                onStartTeachingSession={startTeachingSession}
                onTestDraft={(id) => void testDraftGuided(id)}
                onPublishDraft={(id) => void publishDraft(id)}
                teachingSessionDraftId={teachingSessionDraftId}
                draftsError={errors.drafts}
                teachingTargetWorkerUuid={teachingTargetWorkerUuid}
                setTeachingTargetWorkerUuid={setTeachingTargetWorkerUuid}
                machines={machines}
                workflows={workflows}
                helperWorkflow={helperWorkflow}
                setHelperWorkflow={setHelperWorkflow}
                helperWorkerUuid={helperWorkerUuid}
                setHelperWorkerUuid={setHelperWorkerUuid}
                helperClientName={helperClientName}
                setHelperClientName={setHelperClientName}
                helperHouseholdName={helperHouseholdName}
                setHelperHouseholdName={setHelperHouseholdName}
                helperMaxClients={helperMaxClients}
                setHelperMaxClients={setHelperMaxClients}
                helperMaxPages={helperMaxPages}
                setHelperMaxPages={setHelperMaxPages}
                helperRetryFailedOnly={helperRetryFailedOnly}
                setHelperRetryFailedOnly={setHelperRetryFailedOnly}
                helperFreeText={helperFreeText}
                setHelperFreeText={setHelperFreeText}
                helperBusy={helperBusy}
                helperFeedback={helperFeedback}
                onRunGuidedCommand={() => void runGuidedCommand()}
                onRunFreeTextCommand={() => void runFreeTextCommand()}
                workflowsError={errors.workflows}
                tasks={tasks}
                taskActionBusyKey={taskActionBusyKey}
                taskActionFeedback={taskActionFeedback}
                onCancelTask={(id) => void cancelTask(id)}
                onRetryTask={(task) => void retryFailedTask(task)}
                selectedTask={selectedTask}
                setSelectedTask={setSelectedTask}
                loading={loading}
                actionError={actionError}
                response={response}
                onCreateTestTask={() => void createTestTask()}
                onCreateScreenshotTask={() => void createScreenshotTask()}
                onCreateVisibleWorkflowTask={() => void createVisibleWorkflowTask()}
                onRunSmartSherpa={() => void runSmartSherpaSync()}
                onRunWorkflow={(name) => void runSelectedWorkflow(name)}
                targetMachineUuid={targetMachineUuid}
                setTargetMachineUuid={setTargetMachineUuid}
                workerReleases={workerReleases}
                workerDeployStatus={workerDeployStatus}
                releaseUploadVersion={releaseUploadVersion}
                setReleaseUploadVersion={setReleaseUploadVersion}
                releaseUploadNotes={releaseUploadNotes}
                setReleaseUploadNotes={setReleaseUploadNotes}
                releaseUploadChannel={releaseUploadChannel}
                setReleaseUploadChannel={setReleaseUploadChannel}
                releaseUploadFile={releaseUploadFile}
                setReleaseUploadFile={setReleaseUploadFile}
                releaseUploadBusy={releaseUploadBusy}
                releaseBusyKey={releaseBusyKey}
                releasesFeedback={releasesFeedback}
                deployBusy={deployBusy}
                deployForce={deployForce}
                setDeployForce={setDeployForce}
                deployIdleOnly={deployIdleOnly}
                setDeployIdleOnly={setDeployIdleOnly}
                onUploadRelease={() => void uploadRelease()}
                onActivateRelease={(id) => void activateRelease(id)}
                onDeleteRelease={(id) => void deleteRelease(id)}
                onDeployToWorkers={(uuids) => void deployToWorkers(uuids)}
                onRefreshBrainPanels={() => void loadBrainPanels()}
                chatHistory={chatHistory}
              />
            </div>

            {/* Right column: Workers panel */}
            <div>
              <WorkersPanel
                machines={machines}
                onlineCount={onlineWorkers.length}
                targetMachineUuid={targetMachineUuid}
                setTargetMachineUuid={setTargetMachineUuid}
                renamingMachineUuid={renamingMachineUuid}
                setRenamingMachineUuid={setRenamingMachineUuid}
                renameValue={renameValue}
                setRenameValue={setRenameValue}
                onRename={(uuid, name) => void renameWorker(uuid, name)}
                onDelete={(uuid) => void deleteWorker(uuid)}
                machinesError={errors.machines}
              />
            </div>
          </div>

          {/* System health footer */}
          <SystemHealthFooter
            healthy={!errors.health && (health?.status ?? "").toLowerCase() === "ok"}
            statusText={errors.health ? "Connection error" : "All systems operational"}
            coreVersion={`v${process.env.NEXT_PUBLIC_APP_VERSION ?? "0.3.32"}`}
            lastUpdated={lastUpdated}
            onRefresh={() => { void loadDashboardData(); void loadBrainPanels(); }}
          />
        </div>
      </div>

      {/* ── Mobile Lightweight Interface (hidden on desktop) ─────────────── */}
      <div className="block lg:hidden">
        <MobileDashboard
          mobileView={mobileView}
          onNavigate={setMobileView}
          health={health}
          machines={machines}
          activeTasks={activeTasks}
          failedTasks={failedTasks}
          successfulTasks={successfulTasks}
          humanHelpTasks={humanHelpTasks}
          alerts={alerts}
          resolveBusyKey={resolveBusyKey}
          notificationPermission={notificationPermission}
          chatInput={chatInput}
          setChatInput={setChatInput}
          chatHistory={chatHistory}
          chatLoading={chatLoading}
          onSendCommand={() => void submitBrainCommand()}
          voiceSupported={voiceSupported}
          isListening={isListening}
          isSpeaking={isSpeaking}
          ttsEnabled={ttsEnabled}
          setTtsEnabled={setTtsEnabled}
          startListening={startListening}
          stopListening={stopListening}
          onRetry={(task) => void retryFailedTask(task)}
          onResolve={(taskId) => void resolveHumanHelpTask(taskId)}
          onClearAlert={(id) => setAlerts((a) => a.filter((alert) => alert.id !== id))}
          onClearAll={() => setAlerts([])}
          onRequestNotifications={() => void requestNotificationPermission()}
        />
        <MobileNav
          activeView={mobileView}
          onNavigate={setMobileView}
          urgentCount={humanHelpTasks.length + failedTasks.length}
        />
      </div>

      {teachingSessionDraftId ? (
        <div className="fixed bottom-4 right-4 z-[70] flex max-w-[min(28rem,calc(100vw-2rem))] flex-col items-end gap-3">
          <button
            type="button"
            onClick={() => {
              setTeachingOverlayOpen(true);
              logTeachOverlay("manual overlay open requested", { session_id: teachingSessionDraftId });
            }}
            className="rounded-full border border-cyan-400/40 bg-cyan-500/15 px-4 py-2 text-sm font-semibold text-cyan-100 shadow-lg shadow-cyan-950/40 hover:bg-cyan-500/25"
          >
            Open Teaching Overlay
          </button>

          {teachingOverlayOpen ? (
            <section className="w-full rounded-2xl border border-cyan-400/30 bg-slate-950/95 p-4 text-slate-100 shadow-2xl shadow-slate-950/60 backdrop-blur">
              <div className="flex items-start justify-between gap-3 border-b border-slate-800 pb-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">Teach Overlay Mounted</p>
                  <h2 className="mt-1 text-lg font-semibold text-white">Interactive Teach Mode</h2>
                  <p className="mt-1 text-xs text-slate-400">The overlay stays available even if voice is unavailable.</p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setTeachingOverlayOpen(false)}
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-slate-500 hover:text-white"
                  >
                    Hide
                  </button>
                  <button
                    type="button"
                    onClick={() => void finishTeachingSession()}
                    className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-1.5 text-xs text-rose-200 hover:bg-rose-500/20"
                  >
                    End Session
                  </button>
                </div>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-300 sm:grid-cols-3">
                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2"><span className="text-slate-500">session_id</span><div className="mt-1 break-all text-cyan-100">{teachingSessionDraftId}</div></div>
                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2"><span className="text-slate-500">task_id</span><div className="mt-1 break-all text-cyan-100">{teachingOverlayTaskId ?? "pending"}</div></div>
                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2"><span className="text-slate-500">steps recorded</span><div className={`mt-1 font-bold ${(teachingOverlayQuestion?.steps_recorded ?? 0) > 0 ? "text-emerald-400" : "text-amber-400"}`}>{teachingOverlayQuestion?.steps_recorded ?? 0}</div></div>
                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2"><span className="text-slate-500">question loaded</span><div className="mt-1 text-cyan-100">{String(Boolean(teachingOverlayQuestion?.question))}</div></div>
                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2"><span className="text-slate-500">launch status</span><div className={`mt-1 font-bold ${teachingLaunchStatus === "running" ? "text-emerald-400" : teachingLaunchStatus === "error" ? "text-rose-400" : "text-amber-400"}`}>{teachingLaunchStatus ?? "idle"}</div></div>
                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2"><span className="text-slate-500">current step</span><div className="mt-1 text-cyan-100">{String(teachingOverlayQuestion?.step_order ?? 0)}</div></div>
              </div>

              {teachingLaunchStatus === "error" ? (
                <div className="mt-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                  <p className="font-semibold">Browser launch failed.</p>
                  <p className="mt-1 text-xs">Make sure the Jarvis Worker is running on your computer and a valid Worker UUID and Start URL are set in the Teach Bill form.</p>
                </div>
              ) : teachingLaunchStatus === "running" && (teachingOverlayQuestion?.steps_recorded ?? 0) === 0 ? (
                <div className="mt-3 rounded-xl border border-amber-400/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                  <p className="font-semibold">⚠ No steps recorded yet.</p>
                  <p className="mt-1 text-xs">The task has been queued. The worker will open a <strong>separate Chromium browser window</strong> on the worker computer. Perform your workflow in <em>that</em> browser — actions done here in the dashboard are not captured.</p>
                </div>
              ) : null}

              <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Observation Question</p>
                    <p className="mt-1 text-sm text-slate-300">
                      {teachingOverlayQuestion?.question?.category
                        ? `${teachingOverlayQuestion.question.category} · ${teachingOverlayQuestion.question.trigger_type ?? "prompt"}`
                        : "Waiting for the observed browser to generate a question."}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => teachingSessionDraftId && void loadTeachOverlayQuestion(teachingSessionDraftId)}
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-cyan-400/40 hover:text-cyan-100"
                  >
                    Refresh
                  </button>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void speakTeachOverlayQuestion()}
                    disabled={!teachingOverlayQuestion?.question}
                    className="rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Speak Question
                  </button>
                  <button
                    type="button"
                    onClick={toggleTeachOverlayDictation}
                    disabled={!teachingOverlaySpeechSupported}
                    className="rounded-lg border border-indigo-400/40 bg-indigo-500/10 px-3 py-2 text-sm text-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {teachingOverlayDictating ? "Stop Dictation" : "Start Dictation"}
                  </button>
                </div>

                <div className="mt-3 grid grid-cols-1 gap-2 text-xs text-slate-300 sm:grid-cols-2">
                  <label className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2">
                    <input
                      type="checkbox"
                      checked={teachingOverlayAutoSpeakQuestions}
                      onChange={(event) => {
                        const enabled = event.target.checked;
                        setTeachingOverlayAutoSpeakQuestions(enabled);
                        if (teachingSessionDraftId) {
                          void updateTeachOverlaySettings(teachingSessionDraftId, { auto_speak_questions: enabled });
                        }
                      }}
                    />
                    Auto-speak questions
                  </label>
                  <label className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2">
                    <span>Frequency</span>
                    <select
                      value={teachingOverlayFrequencyMode}
                      onChange={(event) => {
                        const next = event.target.value as "training" | "assisted" | "production";
                        setTeachingOverlayFrequencyMode(next);
                        if (teachingSessionDraftId) {
                          void updateTeachOverlaySettings(teachingSessionDraftId, { question_frequency_mode: next });
                        }
                      }}
                      className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                    >
                      <option value="training">Training</option>
                      <option value="assisted">Assisted</option>
                      <option value="production">Production</option>
                    </select>
                  </label>
                </div>

                <p className="mt-3 min-h-12 text-sm font-medium leading-6 text-white">
                  {teachingOverlayQuestion?.question?.question ?? "No question yet. Perform your workflow in the launched Chromium browser on the worker machine — questions will appear here automatically."}
                </p>

                {teachingOverlayQuestion?.question?.purpose ? (
                  <p className="mt-2 text-xs text-slate-400">Purpose: {teachingOverlayQuestion.question.purpose}</p>
                ) : null}
                {teachingOverlayQuestion?.question?.expected_answer_shape ? (
                  <p className="mt-1 text-xs text-slate-400">Expected: {teachingOverlayQuestion.question.expected_answer_shape}</p>
                ) : null}

                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                  <span className="rounded-full border border-cyan-500/40 bg-cyan-500/10 px-2 py-1 text-cyan-100">
                    State: {teachingOverlayConversationState}
                  </span>
                  {teachingOverlayClarityScore !== null ? (
                    <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200">
                      Clarity: {teachingOverlayClarityScore}
                    </span>
                  ) : null}
                  {teachingOverlayAccepted === true ? (
                    <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-emerald-200">Answer accepted</span>
                  ) : null}
                  {teachingOverlayAccepted === false ? (
                    <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-amber-200">Bill needs clarification</span>
                  ) : null}
                </div>

                {teachingOverlayMissingInfo.length > 0 ? (
                  <p className="mt-2 text-xs text-amber-200">Missing: {teachingOverlayMissingInfo.join("; ")}</p>
                ) : null}
                {teachingOverlayFollowUpText ? (
                  <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                    Follow-up: {teachingOverlayFollowUpText}
                  </p>
                ) : null}
                {teachingOverlayLearnedRulePreview ? (
                  <p className="mt-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-100">
                    Learned rule preview: {JSON.stringify(teachingOverlayLearnedRulePreview)}
                  </p>
                ) : null}

                {teachingOverlayError ? (
                  <p className="mt-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{teachingOverlayError}</p>
                ) : null}

                <textarea
                  value={teachingOverlayAnswer}
                  onChange={(event) => {
                    setTeachingOverlayAnswer(event.target.value);
                    setTeachingOverlayLastTypingAt(Date.now());
                  }}
                  placeholder="Type the employee answer here. Voice is optional and not required for the overlay to work."
                  className="mt-3 min-h-28 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400/60"
                />

                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void submitTeachOverlayAnswer("answer")}
                    disabled={!teachingOverlayQuestion?.question || teachingOverlayBusyKey !== null}
                    className="rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-emerald-950 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Submit Answer
                  </button>
                  <button
                    type="button"
                    onClick={() => void submitTeachOverlayAnswer("skip")}
                    disabled={!teachingOverlayQuestion?.question || teachingOverlayBusyKey !== null}
                    className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Skip Question
                  </button>
                  <button
                    type="button"
                    onClick={() => void toggleTeachOverlayPause()}
                    disabled={teachingOverlayBusyKey !== null}
                    className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {teachingOverlayQuestion?.observation_questions_paused ? "Resume Questions" : "Pause Questions"}
                  </button>
                </div>
              </div>
            </section>
          ) : null}
        </div>
      ) : null}
    </main>
  );
}
