"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
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

type TeachingStartupState = {
  session_id: string;
  task_id?: string | null;
  workflow_name: string;
  target_machine_uuid?: string | null;
  target_machine_name?: string | null;
  status: "browser_opening" | "active" | "failed";
  message?: string;
  overlay_enabled?: boolean;
  voice_prompt_text?: string;
};

type BrowserAction = {
  id: string;
  type: "click" | "type" | "navigate" | "select" | "submit";
  selector?: string;
  label?: string;
  valueRedacted?: string;
  url?: string;
  timestamp: string;
};

type WorkflowStep = {
  id: string;
  order: number;
  title: string;
  observedActions: BrowserAction[];
  employeeExplanation?: string;
  billSummary: string;
  billConfidence: number;
  pendingQuestion?: string;
  reasoningReason?: string;
  needsReasoning: boolean;
  unansweredQuestion: boolean;
  decisionRules: string[];
  exceptions: string[];
  requiredInputs: string[];
  confirmed: boolean;
};

type TeachingSession = {
  sessionId: string;
  workflowName: string;
  workflowSummary?: string;
  status: "intro" | "teaching" | "review" | "approved";
  steps: WorkflowStep[];
};

type TeachingSessionApiResponse = {
  reply: string;
  teaching_session: {
    session_id: string;
    workflow_name: string;
    workflow_summary?: string | null;
    status: "intro" | "teaching" | "review" | "approved";
    steps?: Array<{
      id: string;
      order: number;
      title: string;
      observed_actions?: Array<{
        id: string;
        type: "click" | "type" | "navigate" | "select" | "submit";
        selector?: string | null;
        label?: string | null;
        value_redacted?: string | null;
        url?: string | null;
        timestamp: string;
      }>;
      employee_explanation?: string | null;
      bill_summary?: string;
      bill_confidence?: number;
      pending_question?: string | null;
      reasoning_reason?: string | null;
      needs_reasoning?: boolean;
      unanswered_question?: boolean;
      decision_rules?: string[];
      exceptions?: string[];
      required_inputs?: string[];
      confirmed?: boolean;
    }>;
  };
  review_summary?: {
    workflow_summary?: string;
    total_steps?: number;
    confirmed_steps?: number;
    unconfirmed_steps?: number;
    steps?: Array<{
      step_id: string;
      order: number;
      title: string;
      confirmed: boolean;
      bill_summary?: string;
      employee_explanation?: string | null;
      observed_actions?: Array<{
        id: string;
        type: "click" | "type" | "navigate" | "select" | "submit";
        selector?: string | null;
        label?: string | null;
        value_redacted?: string | null;
        url?: string | null;
        timestamp: string;
      }>;
      decision_rules?: string[];
      exceptions?: string[];
      required_inputs?: string[];
    }>;
  };
  warnings?: string[];
  draft_result?: {
    status?: string;
    action?: string;
    draft_id?: string;
    review_status?: string;
    workflow_name?: string;
  } | null;
};

type TeachingReviewSummary = {
  workflowSummary?: string;
  totalSteps: number;
  confirmedSteps: number;
  unconfirmedSteps: number;
};

type BrainCommandResponse = {
  recognized_intent?: string;
  command?: string;
  before_execution?: string;
  after_execution?: string;
  reply?: string | null;
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
  teaching_mode?: TeachingStartupState | null;
  teaching_session?: TeachingSessionApiResponse["teaching_session"] | null;
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
  voice_provider?: "elevenlabs" | "none";
  browser_tts_enabled?: boolean;
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
  current_stage?: string;
  current_url?: string;
  current_domain?: string;
  last_trigger_event?: string;
  next_question_reason?: string;
  settings?: TeachOverlaySettings;
};

const NEXT_PUBLIC_API_BASE_DEFAULT = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com";
const COMMAND_CENTER_VOICE_PREF_KEY = "bill.command-center.voice.enabled";
const COMMAND_CENTER_AUTO_SUBMIT_PREF_KEY = "bill.command-center.voice.autoSubmit.enabled";
const TEACHING_STARTUP_POLL_TIMEOUT_MS = 60000;
const TEACHING_STARTUP_MAX_POLL_ERRORS = 5;

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
const UUID_LIKE_PATTERN = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i;
const TECHNICAL_SPEECH_PATTERN = /\b(?:task[_\s-]?id|session[_\s-]?id|machine[_\s-]?uuid|uuid|payload|raw json|before:|after:|task queued|debug|trace|stack)\b/i;

const sanitizeTeachingSpeech = (text: string): string | null => {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return null;
  }

  if (UUID_LIKE_PATTERN.test(normalized) || TECHNICAL_SPEECH_PATTERN.test(normalized)) {
    return null;
  }

  if (normalized.startsWith("{") && normalized.endsWith("}")) {
    const colonCount = (normalized.match(/:/g) ?? []).length;
    const keyCount = (normalized.match(/"[^"]+"\s*:/g) ?? []).length;
    if (colonCount >= 3 || keyCount >= 2) {
      return null;
    }
  }

  return normalized;
};

const isEditableTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  const tag = target.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") {
    return true;
  }

  return Boolean(target.isContentEditable || target.closest("[contenteditable='true']"));
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
  const [guidedTeachingSession, setGuidedTeachingSession] = useState<TeachingSession | null>(null);
  const [guidedTeachingMessages, setGuidedTeachingMessages] = useState<ChatEntry[]>([]);
  const [guidedTeachingInput, setGuidedTeachingInput] = useState("");
  const [guidedTeachingBusy, setGuidedTeachingBusy] = useState(false);
  const [guidedTeachingTargetStepId, setGuidedTeachingTargetStepId] = useState<string | null>(null);
  const [guidedTeachingReviewSummary, setGuidedTeachingReviewSummary] = useState<TeachingReviewSummary | null>(null);
  const [guidedTeachingWarnings, setGuidedTeachingWarnings] = useState<string[]>([]);
  const [guidedTeachingApprovalMessage, setGuidedTeachingApprovalMessage] = useState<string | null>(null);
  const [teachingVoiceError, setTeachingVoiceError] = useState<string | null>(null);
  // Teaching startup state — tracks browser_opening → active/failed
  const [teachingStartupState, setTeachingStartupState] = useState<TeachingStartupState | null>(null);
  const teachingStartupPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const teachingStartupTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const teachingStartupPollErrorCountRef = useRef<number>(0);
  const lastSpokenTeachingSessionIdRef = useRef<string>("");
  const lastGuidedTranscriptHashRef = useRef<string>("");
  const lastGuidedTranscriptAtRef = useRef<number>(0);
  const spokenGuidedReplyHashesRef = useRef<Set<string>>(new Set());
  const [pendingTeachingTranscript, setPendingTeachingTranscript] = useState<string | null>(null);
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

  // ── Derived lists ────────────────────────────────────────────────────────────
  const onlineWorkers = machines.filter((m) => m.status === "online" || m.status === "active");
  const activeTasks = tasks.filter((t) => t.status === "running" || t.status === "pending");
  const failedTasks = tasks.filter((t) => t.status === "failed");
  const successfulTasks = tasks.filter((t) => t.status === "completed" || t.status === "success");

  // ── Helpers ───────────────────────────────────────────────────────────────────
  const cloneDraftSteps = (steps: DraftStep[]): DraftStep[] =>
    steps.map((s) => ({ ...s, variable_inputs: [...(s.variable_inputs ?? [])], field_mappings: [...(s.field_mappings ?? [])] }));

  const setFeedback = (
    setter: Dispatch<SetStateAction<ActionFeedback | null>>,
    kind: "success" | "error",
    message: string,
  ) => {
    setter({ kind, message, timestamp: new Date().toLocaleTimeString() });
  };

  const isTechnicalSpeechText = useCallback((text: string | null | undefined): boolean => {
    return sanitizeTeachingSpeech(String(text || "")) === null;
  }, []);

  const getTeachingStartupSpeech = useCallback((body: BrainCommandResponse): string => {
    const candidates = [body.teaching_mode?.voice_prompt_text, body.reply, body.voice_text]
      .map((value) => String(value || "").trim())
      .filter((value) => value.length > 0);

    for (const candidate of candidates) {
      if (!isTechnicalSpeechText(candidate)) {
        return candidate;
      }
    }

    return "";
  }, [isTechnicalSpeechText]);

  const queueBillEventSpeech = (_eventType: string, _context: Record<string, unknown>) => {
    // Voice events handled by useBillVoice hook; this stub satisfies call sites
  };

  const logTeachOverlay = useCallback((message: string, details?: Record<string, unknown>) => {
    console.info("[teach-overlay]", message, details ?? {});
  }, []);

  // ── Teaching startup polling ─────────────────────────────────────────────────
  const stopTeachingStartupPoll = useCallback(() => {
    if (teachingStartupPollRef.current !== null) {
      clearInterval(teachingStartupPollRef.current);
      teachingStartupPollRef.current = null;
    }
    if (teachingStartupTimeoutRef.current !== null) {
      clearTimeout(teachingStartupTimeoutRef.current);
      teachingStartupTimeoutRef.current = null;
    }
    teachingStartupPollErrorCountRef.current = 0;
  }, []);

  const startTeachingStartupPoll = useCallback(
    (sessionId: string) => {
      stopTeachingStartupPoll();
      const apiBase = getApiBase();
      if (!apiBase || !sessionId) return;
      teachingStartupPollErrorCountRef.current = 0;

      const markStartupFailure = (message: string) => {
        setTeachingStartupState((current) => ({
          session_id: sessionId,
          task_id: current?.task_id ?? null,
          workflow_name: current?.workflow_name ?? "Workflow",
          target_machine_uuid: current?.target_machine_uuid ?? null,
          status: "failed",
          message,
          overlay_enabled: true,
          voice_prompt_text: current?.voice_prompt_text,
        }));
        setTeachingOverlayOpen(true);
        stopTeachingStartupPoll();
      };

      teachingStartupTimeoutRef.current = setTimeout(() => {
        logTeachOverlay("startup timeout", {
          session_id: sessionId,
          timeout_ms: TEACHING_STARTUP_POLL_TIMEOUT_MS,
        });
        markStartupFailure(
          "Teaching mode timed out before becoming active. The browser may have opened, but startup confirmation was never received.",
        );
      }, TEACHING_STARTUP_POLL_TIMEOUT_MS);

      teachingStartupPollRef.current = setInterval(async () => {
        try {
          const res = await fetch(`${apiBase}/api/teaching/session/${sessionId}/status`);
          if (!res.ok) {
            teachingStartupPollErrorCountRef.current += 1;
            logTeachOverlay("startup status poll failed", { session_id: sessionId, http_status: res.status });
            if (teachingStartupPollErrorCountRef.current >= TEACHING_STARTUP_MAX_POLL_ERRORS) {
              markStartupFailure(
                "Teaching mode could not confirm startup because status checks are failing. Please retry.",
              );
            }
            return;
          }
          teachingStartupPollErrorCountRef.current = 0;
          const data = (await res.json()) as TeachingStartupState;
          logTeachOverlay("startup status poll", {
            session_id: sessionId,
            status: data.status,
            task_id: data.task_id ?? null,
            message: data.message ?? "",
          });
          if (data.status === "active") {
            console.log("[teaching-browser] active callback received", {
              session_id: sessionId,
              workflow_name: data.workflow_name,
            });
          }
          setTeachingStartupState(data);
          if (data.status === "active" || data.status === "failed") {
            stopTeachingStartupPoll();
          }
        } catch {
          teachingStartupPollErrorCountRef.current += 1;
          logTeachOverlay("startup status poll error", { session_id: sessionId });
          if (teachingStartupPollErrorCountRef.current >= TEACHING_STARTUP_MAX_POLL_ERRORS) {
            markStartupFailure(
              "Teaching mode could not reach the server to confirm startup. Please retry.",
            );
          }
        }
      }, 2000);
    },
    [logTeachOverlay, stopTeachingStartupPoll],
  );

  // Stop polling when component unmounts
  useEffect(() => () => stopTeachingStartupPoll(), [stopTeachingStartupPoll]);

  // ── Voice (Phase 4) ──────────────────────────────────────────────────────────
  const [autoSubmitVoiceCommands, setAutoSubmitVoiceCommands] = useState<boolean>(false);
  const lastAutoSubmittedTranscriptRef = useRef<string>("");
  const lastAutoSubmittedAtRef = useRef<number>(0);
  const { isSupported: voiceSupported, isListening, isSpeaking, ttsEnabled, setTtsEnabled, startListening, stopListening, speak, lastError: voiceLastError } = useVoice({
    onTranscript: (text) => {
      const transcript = text.trim();
      if (!transcript) {
        return;
      }

      setTeachingVoiceError(null);
      setChatInput(transcript);
      if (guidedTeachingSession) {
        setGuidedTeachingInput(transcript);
      }

      const canSendToTeachingChat =
        Boolean(guidedTeachingSession) &&
        Boolean(teachingOverlayOpen) &&
        (guidedTeachingSession?.status === "intro" ||
          guidedTeachingSession?.status === "teaching" ||
          guidedTeachingSession?.status === "review" ||
          teachingStartupState?.status === "browser_opening" ||
          teachingStartupState?.status === "active");

      if (canSendToTeachingChat) {
        const normalized = transcript.replace(/\s+/g, " ").toLowerCase();
        const hash = hashText(`${guidedTeachingSession?.sessionId ?? "session"}|${normalized}`);
        const now = Date.now();
        const isDuplicate =
          hash === lastGuidedTranscriptHashRef.current &&
          now - lastGuidedTranscriptAtRef.current < 8000;

        if (!isDuplicate) {
          lastGuidedTranscriptHashRef.current = hash;
          lastGuidedTranscriptAtRef.current = now;
          setPendingTeachingTranscript(transcript);
          console.log("[teaching-voice] final transcript sent to teaching chat", {
            session_id: guidedTeachingSession?.sessionId ?? null,
          });
        }
        return;
      }

      if (!autoSubmitVoiceCommands) {
        return;
      }

      const normalized = transcript.replace(/\s+/g, " ").toLowerCase();
      const now = Date.now();
      const isDuplicate =
        normalized === lastAutoSubmittedTranscriptRef.current &&
        now - lastAutoSubmittedAtRef.current < 10000;
      if (isDuplicate) {
        return;
      }

      lastAutoSubmittedTranscriptRef.current = normalized;
      lastAutoSubmittedAtRef.current = now;
      void submitBrainCommand(transcript);
    },
  });

  const mapApiTeachingSession = useCallback(
    (input: TeachingSessionApiResponse["teaching_session"]): TeachingSession => ({
      sessionId: input.session_id,
      workflowName: input.workflow_name,
      workflowSummary: input.workflow_summary ?? undefined,
      status: input.status,
      steps: (input.steps ?? []).map((step) => ({
        id: step.id,
        order: step.order,
        title: step.title,
        observedActions: (step.observed_actions ?? []).map((action) => ({
          id: action.id,
          type: action.type,
          selector: action.selector ?? undefined,
          label: action.label ?? undefined,
          valueRedacted: action.value_redacted ?? undefined,
          url: action.url ?? undefined,
          timestamp: action.timestamp,
        })),
        employeeExplanation: step.employee_explanation ?? undefined,
        billSummary: step.bill_summary ?? "",
        billConfidence: Number(step.bill_confidence ?? 0),
        pendingQuestion: step.pending_question ?? undefined,
        reasoningReason: step.reasoning_reason ?? undefined,
        needsReasoning: Boolean(step.needs_reasoning),
        unansweredQuestion: Boolean(step.unanswered_question),
        decisionRules: step.decision_rules ?? [],
        exceptions: step.exceptions ?? [],
        requiredInputs: step.required_inputs ?? [],
        confirmed: Boolean(step.confirmed),
      })),
    }),
    [],
  );

  const applyGuidedTeachingApiResponse = useCallback(
    (body: TeachingSessionApiResponse) => {
      setGuidedTeachingSession(mapApiTeachingSession(body.teaching_session));
      setGuidedTeachingWarnings(body.warnings ?? []);
      if (body.review_summary) {
        setGuidedTeachingReviewSummary({
          workflowSummary: body.review_summary.workflow_summary,
          totalSteps: Number(body.review_summary.total_steps ?? 0),
          confirmedSteps: Number(body.review_summary.confirmed_steps ?? 0),
          unconfirmedSteps: Number(body.review_summary.unconfirmed_steps ?? 0),
        });
      } else {
        setGuidedTeachingReviewSummary(null);
      }
    },
    [mapApiTeachingSession],
  );

  const beginGuidedTeachingSession = useCallback(
    (teachingMode: TeachingStartupState, introReply?: string | null) => {
      setGuidedTeachingSession({
        sessionId: teachingMode.session_id,
        workflowName: teachingMode.workflow_name,
        workflowSummary: undefined,
        status: "intro",
        steps: [],
      });
      setGuidedTeachingInput("");
      setGuidedTeachingReviewSummary(null);
      setGuidedTeachingWarnings([]);
      setGuidedTeachingApprovalMessage(null);
      setGuidedTeachingMessages([
        {
          role: "assistant",
          message:
            introReply?.trim() ||
            `Sounds good. I started a teaching session for ${teachingMode.workflow_name}. Can you give me a quick explanation of what this workflow does?`,
        },
      ]);
    },
    [],
  );

  const formatObservedAction = useCallback((action: BrowserAction): string => {
    if (action.type === "navigate") {
      try {
        const parsed = action.url ? new URL(action.url) : null;
        const path = parsed ? `${parsed.hostname}${parsed.pathname || "/"}` : action.url || "page";
        return `Navigated to ${path}`;
      } catch {
        return `Navigated to ${action.url || "page"}`;
      }
    }
    if (action.type === "type") {
      return `Typed into ${action.label || "field"}`;
    }
    if (action.type === "select") {
      return `Selected option in ${action.label || "field"}`;
    }
    if (action.type === "submit") {
      return `Submitted ${action.label || "form"}`;
    }
    return `Clicked ${action.label || "element"}`;
  }, []);

  const submitGuidedTeachingMessage = useCallback(async (overrideMessage?: string) => {
    if (!guidedTeachingSession || guidedTeachingBusy) return;
    const message = (overrideMessage ?? guidedTeachingInput).trim();
    if (!message) return;

    const targetStepId = guidedTeachingTargetStepId;
    setGuidedTeachingBusy(true);
    setGuidedTeachingMessages((current) => [...current, { role: "user", message }]);
    setGuidedTeachingInput("");

    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const response = await fetch(
        `${apiBase}/api/teaching/session/${guidedTeachingSession.sessionId}/conversation`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message, step_id: targetStepId }),
        },
      );
      const body = (await response.json()) as TeachingSessionApiResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail ?? `Teaching conversation failed (${response.status})`);
      }

      const mapped = mapApiTeachingSession(body.teaching_session);
      setGuidedTeachingSession(mapped);
      setGuidedTeachingReviewSummary(null);
      setGuidedTeachingWarnings([]);
      setGuidedTeachingApprovalMessage(null);
      setGuidedTeachingTargetStepId(null);
      setGuidedTeachingMessages((current) => [...current, { role: "assistant", message: body.reply }]);
    } catch (error) {
      setGuidedTeachingMessages((current) => [
        ...current,
        {
          role: "assistant",
          message: `I couldn't save that teaching note: ${error instanceof Error ? error.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setGuidedTeachingBusy(false);
    }
  }, [guidedTeachingBusy, guidedTeachingInput, guidedTeachingSession, guidedTeachingTargetStepId, mapApiTeachingSession]);

  useEffect(() => {
    if (!pendingTeachingTranscript || !guidedTeachingSession || guidedTeachingBusy) {
      return;
    }

    void submitGuidedTeachingMessage(pendingTeachingTranscript);
    setPendingTeachingTranscript((current) => (current === pendingTeachingTranscript ? null : current));
  }, [pendingTeachingTranscript, guidedTeachingBusy, guidedTeachingSession, submitGuidedTeachingMessage]);

  const confirmGuidedTeachingStep = useCallback(
    async (stepId: string) => {
      if (!guidedTeachingSession || guidedTeachingBusy) return;
      setGuidedTeachingBusy(true);
      try {
        const apiBase = getApiBase();
        if (!apiBase) {
          throw new Error("NEXT_PUBLIC_API_BASE is not set");
        }
        const response = await fetch(
          `${apiBase}/api/teaching/session/${guidedTeachingSession.sessionId}/steps/${stepId}/confirm`,
          { method: "POST" },
        );
        const body = (await response.json()) as TeachingSessionApiResponse & { detail?: string };
        if (!response.ok) {
          throw new Error(body.detail ?? `Step confirmation failed (${response.status})`);
        }
        setGuidedTeachingSession(mapApiTeachingSession(body.teaching_session));
        setGuidedTeachingReviewSummary(null);
        setGuidedTeachingWarnings([]);
        setGuidedTeachingApprovalMessage(null);
        setGuidedTeachingMessages((current) => [...current, { role: "assistant", message: body.reply }]);
      } catch (error) {
        setGuidedTeachingMessages((current) => [
          ...current,
          {
            role: "assistant",
            message: `I couldn't confirm that step: ${error instanceof Error ? error.message : "Unknown error"}`,
          },
        ]);
      } finally {
        setGuidedTeachingBusy(false);
      }
    },
    [guidedTeachingBusy, guidedTeachingSession, mapApiTeachingSession],
  );

  const reviewGuidedTeachingSession = useCallback(async () => {
    if (!guidedTeachingSession || guidedTeachingBusy) return;
    setGuidedTeachingBusy(true);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }
      const response = await fetch(`${apiBase}/api/teaching/session/${guidedTeachingSession.sessionId}/review`, {
        method: "POST",
      });
      const body = (await response.json()) as TeachingSessionApiResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail ?? `Workflow review failed (${response.status})`);
      }
      applyGuidedTeachingApiResponse(body);
      setGuidedTeachingApprovalMessage(null);
      setGuidedTeachingMessages((current) => [...current, { role: "assistant", message: body.reply }]);
    } catch (error) {
      setGuidedTeachingMessages((current) => [
        ...current,
        {
          role: "assistant",
          message: `I couldn't move to workflow review: ${error instanceof Error ? error.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setGuidedTeachingBusy(false);
    }
  }, [applyGuidedTeachingApiResponse, guidedTeachingBusy, guidedTeachingSession]);

  const teachingHotkeyEnabled =
    Boolean(guidedTeachingSession) &&
    Boolean(teachingOverlayOpen) &&
    (guidedTeachingSession?.status === "intro" ||
      guidedTeachingSession?.status === "teaching" ||
      guidedTeachingSession?.status === "review" ||
      teachingStartupState?.status === "browser_opening" ||
      teachingStartupState?.status === "active");

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const isBacktick = event.key === "`" || event.code === "Backquote";
      if (!isBacktick) {
        return;
      }

      if (!teachingHotkeyEnabled) {
        const reason = !guidedTeachingSession
          ? "no_session"
          : !teachingOverlayOpen
            ? "overlay_closed"
            : `status_${guidedTeachingSession.status}`;
        console.log(`[teaching-voice] hotkey ignored reason=${reason}`);
        return;
      }

      if (isEditableTarget(event.target)) {
        console.log("[teaching-voice] hotkey ignored reason=input_focus");
        return;
      }

      event.preventDefault();

      if (!voiceSupported) {
        setTeachingVoiceError("Mic unavailable. Check browser microphone permissions.");
        console.log("[teaching-voice] hotkey ignored reason=mic_unavailable");
        return;
      }

      setTeachingVoiceError(null);
      if (isListening) {
        stopListening();
        return;
      }

      console.log("[teaching-voice] hotkey mic start");
      startListening();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [guidedTeachingSession, isListening, startListening, stopListening, teachingHotkeyEnabled, teachingOverlayOpen, voiceSupported]);

  useEffect(() => {
    if (!voiceLastError || !teachingHotkeyEnabled) {
      return;
    }
    setTeachingVoiceError(`Mic error: ${voiceLastError}`);
  }, [teachingHotkeyEnabled, voiceLastError]);

  useEffect(() => {
    if (!guidedTeachingSession?.sessionId) {
      spokenGuidedReplyHashesRef.current.clear();
      return;
    }
    spokenGuidedReplyHashesRef.current.clear();
  }, [guidedTeachingSession?.sessionId]);

  const continueGuidedTeachingSession = useCallback(async () => {
    if (!guidedTeachingSession || guidedTeachingBusy) return;
    setGuidedTeachingBusy(true);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }
      const response = await fetch(`${apiBase}/api/teaching/session/${guidedTeachingSession.sessionId}/continue`, {
        method: "POST",
      });
      const body = (await response.json()) as TeachingSessionApiResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail ?? `Continue teaching failed (${response.status})`);
      }
      setGuidedTeachingSession(mapApiTeachingSession(body.teaching_session));
      setGuidedTeachingReviewSummary(null);
      setGuidedTeachingWarnings([]);
      setGuidedTeachingApprovalMessage(null);
      setGuidedTeachingMessages((current) => [...current, { role: "assistant", message: body.reply }]);
    } catch (error) {
      setGuidedTeachingMessages((current) => [
        ...current,
        {
          role: "assistant",
          message: `I couldn't continue teaching mode: ${error instanceof Error ? error.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setGuidedTeachingBusy(false);
    }
  }, [guidedTeachingBusy, guidedTeachingSession, mapApiTeachingSession]);

  const approveGuidedTeachingSession = useCallback(async () => {
    if (!guidedTeachingSession || guidedTeachingBusy) return;
    setGuidedTeachingBusy(true);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }
      const response = await fetch(`${apiBase}/api/teaching/session/${guidedTeachingSession.sessionId}/approve`, {
        method: "POST",
      });
      const body = (await response.json()) as TeachingSessionApiResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail ?? `Approve workflow failed (${response.status})`);
      }
      applyGuidedTeachingApiResponse(body);
      setGuidedTeachingApprovalMessage("Workflow approved. Bill created a playbook draft for review.");
      setGuidedTeachingMessages((current) => [...current, { role: "assistant", message: body.reply }]);
    } catch (error) {
      setGuidedTeachingMessages((current) => [
        ...current,
        {
          role: "assistant",
          message: `I couldn't approve this workflow yet: ${error instanceof Error ? error.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setGuidedTeachingBusy(false);
    }
  }, [applyGuidedTeachingApiResponse, guidedTeachingBusy, guidedTeachingSession]);
  const billVoice = useBillVoice(getApiBase());
  const commandMic = useBillMic();
  const [commandVoiceEnabled, setCommandVoiceEnabled] = useState<boolean>(true);
  const [commandVoiceEmotion, setCommandVoiceEmotion] = useState<string>("helpful");
  const [commandVoiceStyleProfile, setCommandVoiceStyleProfile] = useState<string>("default");
  const [lastCommandResponseText, setLastCommandResponseText] = useState<string>("");
  const lastSpokenHashRef = useRef<string>("");
  const lastSpokenAtRef = useRef<number>(0);
  const lastTeachOverlaySpokenPromptRef = useRef<string>("");
  const lastTeachOverlaySpeakInFlightRef = useRef<string>("");
  const lastVoiceEventRef = useRef<{ eventType: string; at: number }>({ eventType: "", at: 0 });
  const teachRecognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const teachingOverlayVoiceEnabled = Boolean(
    commandVoiceEnabled && billVoice.config?.voice_enabled && billVoice.config?.configured,
  );
  const teachingOverlayVoiceIssue = useMemo(() => {
    if (!commandVoiceEnabled) {
      return "Command Center voice is turned off.";
    }
    if (!billVoice.config) {
      return billVoice.lastError
        ? `Voice config check failed: ${billVoice.lastError}`
        : "Voice config is still loading.";
    }
    if (!billVoice.config.voice_enabled) {
      return "Backend voice is disabled (BILL_VOICE_ENABLED is false).";
    }
    if (!billVoice.config.configured) {
      return billVoice.config.reason ?? "ElevenLabs API key/voice ID is missing.";
    }
    return null;
  }, [billVoice.config, billVoice.lastError, commandVoiceEnabled]);

  // ── Voice: speak once when teaching browser transitions to active ──────────
  useEffect(() => {
    if (!teachingStartupState) return;
    const { session_id, status, voice_prompt_text } = teachingStartupState;
    if (status !== "active") return;
    if (lastSpokenTeachingSessionIdRef.current === session_id) return;
    lastSpokenTeachingSessionIdRef.current = session_id;
    const promptText = voice_prompt_text?.trim() || "Teaching mode is active. Walk me through what this workflow is for.";
    if (isTechnicalSpeechText(promptText)) {
      console.log("[teaching-voice] skipped technical speech", {
        phase: "active",
        session_id,
      });
      return;
    }
    logTeachOverlay("voice prompt trigger", {
      session_id,
      status,
      voice_provider: commandVoiceEnabled && billVoice.config?.voice_enabled && billVoice.config?.configured ? "bill_voice" : "browser_tts",
      prompt_preview: promptText.slice(0, 120),
    });
    console.log("[teaching-voice] speaking active prompt", {
      session_id,
      workflow_name: teachingStartupState.workflow_name,
    });

    void (async () => {
      const spoken = commandVoiceEnabled && billVoice.config?.voice_enabled && billVoice.config?.configured
        ? await billVoice.speakText({
            text: promptText,
            emotion: commandVoiceEmotion,
            style_profile: commandVoiceStyleProfile,
            task_id: teachingStartupState.task_id ?? undefined,
            workflow_name: teachingStartupState.workflow_name,
            context: {
              event_type: "teaching_mode_active",
              source: "teaching_startup_status",
              session_id,
            },
          })
        : false;

      if (!spoken) {
        speak(promptText);
      }
    })();
  }, [
    teachingStartupState,
    commandVoiceEnabled,
    billVoice,
    commandVoiceEmotion,
    commandVoiceStyleProfile,
    isTechnicalSpeechText,
    logTeachOverlay,
    speak,
  ]);

  useEffect(() => {
    if (!guidedTeachingSession || guidedTeachingMessages.length === 0) {
      return;
    }

    const latestAssistant = [...guidedTeachingMessages].reverse().find((entry) => entry.role === "assistant");
    if (!latestAssistant) {
      return;
    }

    const dedupeHash = hashText(`${guidedTeachingSession.sessionId}|${latestAssistant.message}`);
    if (spokenGuidedReplyHashesRef.current.has(dedupeHash)) {
      console.log("[teaching-voice] skipped duplicate reply", {
        session_id: guidedTeachingSession.sessionId,
      });
      return;
    }

    spokenGuidedReplyHashesRef.current.add(dedupeHash);
    const sanitized = sanitizeTeachingSpeech(latestAssistant.message);
    if (!sanitized) {
      console.log("[teaching-voice] skipped technical reply", {
        session_id: guidedTeachingSession.sessionId,
      });
      return;
    }

    console.log("[teaching-voice] speaking floating chat reply", {
      session_id: guidedTeachingSession.sessionId,
    });

    void (async () => {
      const spoken = commandVoiceEnabled && billVoice.config?.voice_enabled && billVoice.config?.configured
        ? await billVoice.speakText({
            text: sanitized,
            emotion: commandVoiceEmotion,
            style_profile: commandVoiceStyleProfile,
            workflow_name: guidedTeachingSession.workflowName,
            context: {
              event_type: "teaching_floating_chat_reply",
              session_id: guidedTeachingSession.sessionId,
            },
          })
        : false;

      if (!spoken) {
        speak(sanitized);
      }
    })();
  }, [
    billVoice,
    commandVoiceEmotion,
    commandVoiceEnabled,
    commandVoiceStyleProfile,
    guidedTeachingMessages,
    guidedTeachingSession,
    speak,
  ]);

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

  useEffect(() => {
    if (guidedTeachingSession?.status !== "approved") {
      return;
    }
    void loadBrainPanels();
  }, [guidedTeachingSession?.status]);

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
      if (slug === "smart_sherpa_sync") {
        requestBody.payload = {
          run_mode: "batch",
          source_record: { run_mode: "batch" },
          target_contact: { run_mode: "batch" },
        };
      }
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
        payload: {
          run_mode: "batch",
          source_record: { run_mode: "batch" },
          target_contact: { run_mode: "batch" },
        }
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

  async function submitBrainCommand(
    commandOverride?: string,
    workerOverrideUuid?: string,
  ) {
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

      // For teaching-start commands, show the conversational reply in chat instead of
      // technical Before/After/Task-ID details (which expose internals to the employee).
      const isTeachingStart = body.recognized_intent === "start_new_workflow";
      const chatMessage = isTeachingStart && body.reply
        ? body.reply
        : lines.join("\n");

      setChatHistory((current) => [
        ...current,
        {
          role: "assistant",
          message: chatMessage,
          suggestedNextAction: body.suggested_next_action ?? undefined,
        },
      ]);
      setLastCommandResponseText(isTeachingStart && body.reply ? body.reply : lines.join(". "));

      let responseVoiceText = (body.voice_text ?? "").trim() || lines.join(". ");
      if (isTeachingStart) {
        responseVoiceText = getTeachingStartupSpeech(body);
        if (!responseVoiceText) {
          console.log("[teaching-voice] skipped technical speech", {
            phase: "startup",
            recognized_intent: body.recognized_intent,
          });
        }
      }

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
          if (isTeachingStart) {
            console.log("[teaching-voice] speaking startup prompt", {
              workflow_name: body.selected_workflow ?? body.teaching_mode?.workflow_name ?? null,
            });
          }
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

      if (!isTeachingStart && body.task?.id && body.selected_workflow) {
        queueBillEventSpeech("workflow_started", {
          taskId: body.task.id,
          workflowName: body.selected_workflow,
          context: { source: "brain_command" },
        });
      }

      // ── Teaching startup ──────────────────────────────────────────────────
      if (body.teaching_mode?.session_id) {
        console.log("[teaching-apprentice] command response received", {
          session_id: body.teaching_mode.session_id,
          workflow_name: body.teaching_mode.workflow_name,
          has_teaching_session: Boolean(body.teaching_session),
          recognized_intent: body.recognized_intent,
        });
        console.log("[teaching-browser] waiting for worker browser callback", {
          session_id: body.teaching_mode.session_id,
          worker_name: body.teaching_mode.target_machine_name ?? body.selected_worker_name ?? null,
        });
        logTeachOverlay("teaching_mode response received", {
          session_id: body.teaching_mode.session_id,
          status: body.teaching_mode.status,
          task_id: body.teaching_mode.task_id ?? null,
          workflow_name: body.teaching_mode.workflow_name,
        });
        setTeachingStartupState(body.teaching_mode);
        if (body.teaching_mode.overlay_enabled !== false) {
          logTeachOverlay("overlay activation requested", {
            session_id: body.teaching_mode.session_id,
            source: "brain_command_response",
          });
          setTeachingOverlayOpen(true);
        }
        if (body.teaching_session) {
          setGuidedTeachingSession(mapApiTeachingSession(body.teaching_session));
          setGuidedTeachingInput("");
          setGuidedTeachingReviewSummary(null);
          setGuidedTeachingWarnings([]);
          setGuidedTeachingApprovalMessage(null);
          setGuidedTeachingMessages([
            {
              role: "assistant",
              message:
                body.reply?.trim() ||
                `Sounds good. I started a teaching session for ${body.teaching_session.workflow_name}. Can you give me a quick explanation of what this workflow does?`,
            },
          ]);
        } else {
          beginGuidedTeachingSession(body.teaching_mode, body.reply);
        }
        console.log("[teaching-apprentice] session initialized", {
          session_id: body.teaching_mode.session_id,
          workflow_name: body.teaching_session?.workflow_name ?? body.teaching_mode.workflow_name,
          status: body.teaching_session?.status ?? "intro",
        });
        console.log("[teaching-apprentice] showing apprentice panel");
        startTeachingStartupPoll(body.teaching_mode.session_id);
      } else if (body.recognized_intent === "start_new_workflow") {
        const reason = body.task?.id
          ? "teaching_mode missing in response despite task created"
          : "no worker available or session creation failed";
        console.log("[teaching-apprentice] fell back to legacy teaching UI", { reason, task_id: body.task?.id ?? null });
        logTeachOverlay("teaching_mode missing in response", {
          task_id: body.task?.id ?? null,
          recognized_intent: body.recognized_intent,
          selected_workflow: body.selected_workflow ?? null,
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
  }

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
    async (draftId: string, options?: { silent?: boolean; force?: boolean }) => {
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
        const forceParam = options?.force ? "?force=true" : "";
        const response = await fetch(`${apiBase}/api/teach-sessions/${draftId}/questions/next${forceParam}`);
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
      voice_provider: "elevenlabs",
      browser_tts_enabled: false,
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

  const speakTeachOverlayQuestion = useCallback(async (options?: { isAuto?: boolean }): Promise<boolean> => {
    const text = teachingOverlayQuestion?.question?.question?.trim();
    const promptId = String(teachingOverlayQuestion?.question?.prompt_id || "");
    if (!text) {
      return false;
    }
    const provider = String(teachingOverlayQuestion?.settings?.voice_provider || "elevenlabs").trim().toLowerCase();

    logTeachOverlay("auto_speak_requested", {
      provider,
      question_id: promptId,
      auto: Boolean(options?.isAuto),
      skipped_duplicate: false,
      browser_tts_disabled: true,
    });

    if (provider !== "elevenlabs") {
      logTeachOverlay("auto_speak_requested", {
        provider,
        question_id: promptId,
        auto: Boolean(options?.isAuto),
        skipped_duplicate: true,
        browser_tts_disabled: true,
      });
      return false;
    }

    if (!teachingOverlayVoiceEnabled) {
      setTeachingOverlayError(`ElevenLabs voice is not configured for this session. ${teachingOverlayVoiceIssue ?? ""}`.trim());
      return false;
    }

    const played = await billVoice.speakText({
      text,
      emotion: commandVoiceEmotion,
      style_profile: commandVoiceStyleProfile,
      task_id: teachingOverlayTaskId ?? undefined,
      context: {
        source: "teach_overlay_question",
        session_id: teachingSessionDraftId,
        prompt_id: promptId,
        auto: Boolean(options?.isAuto),
      },
    });

    logTeachOverlay("auto_speak_requested", {
      provider: "elevenlabs",
      question_id: promptId,
      auto: Boolean(options?.isAuto),
      skipped_duplicate: false,
      browser_tts_disabled: true,
      played,
    });

    if (!played) {
      setTeachingOverlayError("ElevenLabs voice playback failed.");
    }
    return played;
  }, [
    billVoice,
    commandVoiceEmotion,
    commandVoiceStyleProfile,
    logTeachOverlay,
    teachingOverlayQuestion,
    teachingOverlayTaskId,
    teachingOverlayVoiceIssue,
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
    const promptId = String(teachingOverlayQuestion?.question?.prompt_id || "");
    if (!teachingOverlayOpen || !promptId || !teachingOverlayAutoSpeakQuestions) {
      return;
    }
    if (lastTeachOverlaySpokenPromptRef.current === promptId) {
      logTeachOverlay("auto_speak_requested", {
        provider: String(teachingOverlayQuestion?.settings?.voice_provider || "elevenlabs"),
        question_id: promptId,
        auto: true,
        skipped_duplicate: true,
        browser_tts_disabled: true,
      });
      return;
    }
    if (lastTeachOverlaySpeakInFlightRef.current === promptId) {
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
    lastTeachOverlaySpeakInFlightRef.current = promptId;
    void speakTeachOverlayQuestion({ isAuto: true })
      .then((played) => {
        if (played) {
          lastTeachOverlaySpokenPromptRef.current = promptId;
          lastSpokenAtRef.current = Date.now();
        }
      })
      .finally(() => {
        if (lastTeachOverlaySpeakInFlightRef.current === promptId) {
          lastTeachOverlaySpeakInFlightRef.current = "";
        }
      });
  }, [
    logTeachOverlay,
    speakTeachOverlayQuestion,
    teachingOverlayAutoSpeakQuestions,
    teachingOverlayLastTypingAt,
    teachingOverlayOpen,
    teachingOverlayQuestion?.question?.prompt_id,
    teachingOverlayQuestion?.settings?.do_not_ask_while_user_typing,
    teachingOverlayQuestion?.settings?.min_seconds_between_questions,
    teachingOverlayQuestion?.settings?.voice_provider,
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
                autoSubmitVoiceCommands={autoSubmitVoiceCommands}
                setAutoSubmitVoiceCommands={setAutoSubmitVoiceCommands}
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

      {guidedTeachingSession ? (
        <div className="fixed bottom-4 right-4 z-[70] flex max-w-[min(32rem,calc(100vw-2rem))] flex-col items-end gap-3">
          <button
            type="button"
            onClick={() => {
              setTeachingOverlayOpen(true);
              logTeachOverlay("manual overlay open requested", { session_id: guidedTeachingSession.sessionId });
            }}
            className="rounded-full border border-cyan-400/40 bg-cyan-500/15 px-4 py-2 text-sm font-semibold text-cyan-100 shadow-lg shadow-cyan-950/40 hover:bg-cyan-500/25"
          >
            Open Teaching Mode
          </button>

          {teachingStartupState && teachingStartupState.status !== "active" && (
            <section
              className={`w-full rounded-2xl border p-4 text-slate-100 shadow-2xl backdrop-blur ${
                teachingStartupState.status === "failed"
                  ? "border-rose-500/40 bg-rose-950/80"
                  : "border-cyan-400/30 bg-slate-950/95"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">Teaching Mode</p>
                  <h3 className="text-sm font-semibold text-white">
                    {teachingStartupState.status === "browser_opening"
                      ? `Opening teaching browser on ${teachingStartupState.target_machine_name || "selected worker"}`
                      : `Teaching browser failed for ${teachingStartupState.workflow_name}`}
                  </h3>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {teachingStartupState.status === "browser_opening"
                      ? "Waiting for worker confirmation..."
                      : "Bill could not open the teaching browser. Restart the worker and try again."}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    stopTeachingStartupPoll();
                    setTeachingStartupState(null);
                  }}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-slate-500 hover:text-white"
                >
                  Dismiss
                </button>
              </div>
            </section>
          )}

          {teachingOverlayOpen ? (
            <section className="w-full rounded-2xl border border-cyan-400/30 bg-slate-950/95 p-4 text-slate-100 shadow-2xl shadow-slate-950/60 backdrop-blur">
              <div className="flex items-start justify-between gap-3 border-b border-slate-800 pb-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">Teaching Mode Active</p>
                  <h2 className="mt-1 text-lg font-semibold text-white">{guidedTeachingSession.workflowName}</h2>
                  <p className="mt-1 text-xs text-slate-400">Train Bill like a new hire while you work.</p>
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
                    onClick={() => void reviewGuidedTeachingSession()}
                    disabled={guidedTeachingBusy || guidedTeachingSession.status === "review" || guidedTeachingSession.status === "approved"}
                    className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-100 hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    End Teaching / Review Workflow
                  </button>
                </div>
              </div>

              {(guidedTeachingSession.status === "review" || guidedTeachingSession.status === "approved" || guidedTeachingReviewSummary) && (
                <section className="mt-4 rounded-xl border border-amber-500/30 bg-amber-950/25 p-3">
                  <p className="text-xs uppercase tracking-[0.16em] text-amber-200">Review Workflow</p>
                  <p className="mt-1 text-sm text-amber-50">
                    {guidedTeachingReviewSummary?.workflowSummary || guidedTeachingSession.workflowSummary || "Review captured steps before final approval."}
                  </p>
                  <p className="mt-2 text-xs text-amber-100/90">
                    Steps: {guidedTeachingReviewSummary?.totalSteps ?? guidedTeachingSession.steps.length} | Confirmed: {guidedTeachingReviewSummary?.confirmedSteps ?? guidedTeachingSession.steps.filter((step) => step.confirmed).length} | Unconfirmed: {guidedTeachingReviewSummary?.unconfirmedSteps ?? guidedTeachingSession.steps.filter((step) => !step.confirmed).length}
                  </p>
                  {(guidedTeachingWarnings.includes("Some steps are not confirmed yet. You can approve anyway, but Bill may need more training.") || (guidedTeachingReviewSummary?.unconfirmedSteps ?? 0) > 0) && (
                    <p className="mt-2 rounded-md border border-amber-400/40 bg-amber-400/10 px-2 py-1.5 text-xs text-amber-100">
                      Some steps are not confirmed yet. You can approve anyway, but Bill may need more training.
                    </p>
                  )}
                  {guidedTeachingApprovalMessage && (
                    <p className="mt-2 rounded-md border border-emerald-400/40 bg-emerald-400/10 px-2 py-1.5 text-xs text-emerald-100">
                      Workflow approved. Bill created a playbook draft for review.
                    </p>
                  )}
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void reviewGuidedTeachingSession()}
                      disabled={guidedTeachingBusy || guidedTeachingSession.status === "review" || guidedTeachingSession.status === "approved"}
                      className="rounded border border-amber-400/40 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      Review Workflow
                    </button>
                    <button
                      type="button"
                      onClick={() => void continueGuidedTeachingSession()}
                      disabled={guidedTeachingBusy}
                      className="rounded border border-slate-600 px-2.5 py-1.5 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      Continue Teaching
                    </button>
                    <button
                      type="button"
                      onClick={() => void approveGuidedTeachingSession()}
                      disabled={guidedTeachingBusy}
                      className="rounded border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1.5 text-xs text-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      Approve Workflow
                    </button>
                  </div>
                </section>
              )}

              <div className="mt-4 grid grid-cols-1 gap-3">
                <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                  <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Floating Chat Panel</p>
                  <p className="mt-1 text-xs text-slate-400">Press ` to talk to Bill</p>
                  <p className="mt-1 text-xs text-indigo-200">
                    {!voiceSupported
                      ? "Mic unavailable"
                      : isListening
                        ? "Listening..."
                        : pendingTeachingTranscript || guidedTeachingBusy
                          ? "Processing..."
                          : "Ready"}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">Bill will speak his replies aloud.</p>
                  {teachingVoiceError && (
                    <p className="mt-2 rounded-md border border-rose-400/40 bg-rose-500/10 px-2 py-1.5 text-xs text-rose-100">
                      {teachingVoiceError}
                    </p>
                  )}
                  <div className="mt-2 max-h-40 space-y-2 overflow-auto pr-1 text-sm">
                    {guidedTeachingMessages.map((entry, index) => (
                      <div
                        key={`${entry.role}-${index}`}
                        className={`rounded-lg px-3 py-2 ${entry.role === "assistant" ? "bg-cyan-500/10 text-cyan-100" : "bg-slate-800 text-slate-100"}`}
                      >
                        {entry.message}
                      </div>
                    ))}
                  </div>
                  <textarea
                    value={guidedTeachingInput}
                    onChange={(event) => setGuidedTeachingInput(event.target.value)}
                    placeholder={guidedTeachingTargetStepId ? "Add detail for selected step..." : "Explain what you're doing as you work..."}
                    className="mt-3 min-h-20 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400/60"
                  />
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void submitGuidedTeachingMessage()}
                      disabled={guidedTeachingBusy || !guidedTeachingInput.trim()}
                      className="rounded-lg bg-cyan-500 px-3 py-2 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Send to Bill
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (isListening) {
                          stopListening();
                        } else {
                          startListening();
                        }
                      }}
                      className="rounded-lg border border-indigo-400/40 bg-indigo-500/10 px-3 py-2 text-sm text-indigo-100"
                    >
                      {isListening ? "Stop Voice" : "Speak Reply"}
                    </button>
                  </div>
                </section>

                <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                  <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Live Workflow Step Cards</p>
                  <div className="mt-2 max-h-[46vh] space-y-2 overflow-y-auto pr-1">
                    {guidedTeachingSession.steps.length === 0 ? (
                      <div className="rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-3 text-sm text-slate-300">
                        Step cards are ready. As you teach, Bill will add summarized steps here.
                      </div>
                    ) : (
                      guidedTeachingSession.steps.map((step) => (
                        <article key={step.id} className="rounded-lg border border-slate-700 bg-slate-950/70 p-3 text-sm">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Step {step.order}</p>
                              <h3 className="mt-1 font-semibold text-white">{step.title}</h3>
                            </div>
                            <span className={`rounded-full border px-2 py-1 text-[10px] ${step.confirmed ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-200" : "border-amber-400/40 bg-amber-500/10 text-amber-100"}`}>
                              {step.confirmed ? "Confirmed" : "Needs Confirmation"}
                            </span>
                          </div>
                          <p className="mt-2 text-slate-300">{step.billSummary || "Bill is still summarizing this step."}</p>
                          <div className="mt-2 rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-2">
                            <p className="text-[11px] uppercase tracking-[0.14em] text-cyan-200">What Bill thinks he learned</p>
                            <p className="mt-1 text-xs text-cyan-100">{step.billSummary || "Bill is still interpreting this step."}</p>
                            <p className="mt-1 text-[11px] text-cyan-200/90">Confidence: {(Math.max(0, Math.min(1, step.billConfidence || 0)) * 100).toFixed(0)}%</p>
                            {step.pendingQuestion && (
                              <p className="mt-1 text-xs text-cyan-50">{step.pendingQuestion}</p>
                            )}
                          </div>
                          <div className="mt-2 rounded-md border border-slate-800 bg-slate-900/60 px-2.5 py-2">
                            <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">Observed browser actions</p>
                            {step.observedActions.length === 0 ? (
                              <p className="mt-1 text-xs text-slate-400">No browser actions captured yet.</p>
                            ) : (
                              <ul className="mt-1 space-y-1 text-xs text-slate-300">
                                {step.observedActions.map((action) => (
                                  <li key={action.id}>{formatObservedAction(action)}</li>
                                ))}
                              </ul>
                            )}
                          </div>
                          <p className="mt-2 text-xs text-slate-400">Employee explanation: {step.employeeExplanation || "Pending"}</p>
                          <p className="mt-1 text-xs text-slate-400">Required data: {step.requiredInputs.join(", ") || "Pending"}</p>
                          <p className="mt-1 text-xs text-slate-400">Decision rules: {step.decisionRules.join("; ") || "None yet"}</p>
                          <p className="mt-1 text-xs text-slate-400">Exceptions: {step.exceptions.join("; ") || "None yet"}</p>
                          <div className="mt-2 flex gap-2">
                            <button
                              type="button"
                              onClick={() => void confirmGuidedTeachingStep(step.id)}
                              disabled={guidedTeachingBusy || step.confirmed}
                              className="rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              Yes
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setGuidedTeachingTargetStepId(step.id);
                                setGuidedTeachingInput(`Not quite for Step ${step.order}: `);
                              }}
                              className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-200"
                            >
                              Not quite
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setGuidedTeachingTargetStepId(step.id);
                                setGuidedTeachingInput(`Additional detail for Step ${step.order}: `);
                              }}
                              className="rounded border border-cyan-500/40 bg-cyan-500/10 px-2 py-1 text-xs text-cyan-100"
                            >
                              Add detail
                            </button>
                          </div>
                        </article>
                      ))
                    )}
                  </div>
                </section>
              </div>
            </section>
          ) : null}
        </div>
      ) : null}
    </main>
  );
}
