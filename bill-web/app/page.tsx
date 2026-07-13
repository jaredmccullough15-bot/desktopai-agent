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
import { SuperAdminControlPlane } from "./components/SuperAdminControlPlane";
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
  draft_id?: string | null;
  workflow_name: string;
  target_machine_uuid?: string | null;
  target_machine_name?: string | null;
  status: "browser_opening" | "active" | "failed";
  message?: string;
  overlay_enabled?: boolean;
  voice_prompt_text?: string;
  teaching_session?: TeachingSessionApiResponse["teaching_session"] | null;
  start_url?: string | null;
  suggested_start_url?: string | null;
  observed_current_page?: string | null;
  extension_connection_status?: string | null;
  extension_event_count?: number;
  latest_extension_event?: Record<string, unknown> | null;
  steps?: TeachingSessionApiResponse["teaching_session"]["steps"];
  page_context_snapshot?: TeachingSessionApiResponse["teaching_session"]["page_context_snapshot"];
  copilot_notice?: string | null;
  copilot_interpretation?: string | null;
  copilot_question?: string | null;
};

type BrowserAction = {
  id: string;
  type: "click" | "type" | "navigate" | "select" | "submit" | "focus";
  source?: "browser" | "extension" | "manual";
  selector?: string;
  selectors?: string[];
  label?: string;
  target_label?: string;
  target_type?: string;
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
  status: "intro" | "teaching" | "review" | "approved" | "ready" | "needs_more_teaching";
  startUrl?: string;
  observedStartUrl?: string;
  suggestedStartUrl?: string;
  observedCurrentPage?: string;
  steps: WorkflowStep[];
  extensionConnectionStatus?: string | null;
  extensionEventCount?: number;
  lastExtensionEvent?: Record<string, unknown> | null;
  extensionEvents?: Record<string, unknown>[];
  pageContextSnapshot?: {
    url?: string;
    title?: string;
    domain?: string;
    visible_buttons?: Array<{ text?: string; aria_label?: string; role?: string; selector_hint?: string | null }>;
    visible_inputs?: Array<{ label?: string; placeholder?: string; type?: string; name?: string; selector_hint?: string | null; sensitive?: boolean }>;
    visible_links?: Array<{ text?: string; href?: string }>;
    visible_headings?: Array<{ text?: string; level?: number | null }>;
    buttons?: string[];
    inputs?: Array<{ label?: string; placeholder?: string; type?: string }>;
    links?: string[];
    headings?: string[];
    active_element?: { type?: string; label?: string } | null;
    recent_click_label?: string | null;
    recent_type_field?: string | null;
    extension_connection_status?: string | null;
    extension_event_count?: number;
    last_extension_event?: Record<string, unknown> | null;
    modal_present?: boolean;
    modal_title?: string | null;
    captured_at?: number;
  } | null;
};

type GuidedStepEditState = {
  title: string;
  employeeExplanation: string;
  billSummary: string;
  decisionRules: string;
  exceptions: string;
  requiredInputs: string;
};

type TeachingSessionApiResponse = {
  reply: string;
  copilot_notice?: string | null;
  copilot_interpretation?: string | null;
  copilot_question?: string | null;
  teaching_session: {
    session_id: string;
    workflow_name: string;
    workflow_summary?: string | null;
    status: "intro" | "teaching" | "review" | "approved";
    start_url?: string | null;
    observed_start_url?: string | null;
    suggested_start_url?: string | null;
    observed_current_page?: string | null;
    extension_connection_status?: string | null;
    extension_event_count?: number;
    last_extension_event?: Record<string, unknown> | null;
    extension_events?: Record<string, unknown>[];
    page_context_snapshot?: {
      url?: string;
      title?: string;
      domain?: string;
      visible_buttons?: Array<{ text?: string; aria_label?: string; role?: string; selector_hint?: string | null }>;
      visible_inputs?: Array<{ label?: string; placeholder?: string; type?: string; name?: string; selector_hint?: string | null; sensitive?: boolean }>;
      visible_links?: Array<{ text?: string; href?: string }>;
      visible_headings?: Array<{ text?: string; level?: number | null }>;
      buttons?: string[];
      inputs?: Array<{ label?: string; placeholder?: string; type?: string }>;
      links?: string[];
      headings?: string[];
      active_element?: { type?: string; label?: string } | null;
      recent_click_label?: string | null;
      recent_type_field?: string | null;
      extension_connection_status?: string | null;
      extension_event_count?: number;
      last_extension_event?: Record<string, unknown> | null;
      modal_present?: boolean;
      modal_title?: string | null;
      captured_at?: number;
    } | null;
    steps?: Array<{
      id: string;
      order: number;
      title: string;
      observed_actions?: Array<{
        id: string;
        type: "click" | "type" | "navigate" | "select" | "submit" | "focus";
        source?: "browser" | "extension" | "manual";
        selector?: string | null;
        selectors?: string[];
        label?: string | null;
        target_label?: string | null;
        target_type?: string | null;
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
  execution_readiness?: {
    runnable?: boolean;
    has_start_url?: boolean;
    start_url?: string | null;
    blocking_reasons?: string[];
    execution_warnings?: string[];
  } | null;
};

const INVALID_TEACHING_CONTEXT_MARKERS = ["omnibox-popup", "top-chrome", "chrome://", "chrome-extension://", "devtools://", "about:", "edge://", "extension://"];
const INVALID_TEACHING_CONTEXT_MESSAGE = "Bill is waiting for the real webpage tab.";

const BILL_CAN_SEE_PANEL_COPY = {
  heading: "Bill can currently see",
  waitingMessage: "Bill is waiting for the real webpage tab.",
  waitingBadge: "Waiting for real webpage tab",
  invalidMarkers: ["omnibox-popup", "top-chrome"],
  floatingPanelLabel: "Floating Chat Panel",
} as const;

function isInvalidTeachingContextSnapshot(snapshot: { url?: string; title?: string; domain?: string } | null | undefined): boolean {
  const urlValue = snapshot?.url || "";
  const titleValue = snapshot?.title || "";
  const domainValue = snapshot?.domain || "";
  const lowered = `${urlValue} ${titleValue} ${domainValue}`.toLowerCase();
  return INVALID_TEACHING_CONTEXT_MARKERS.some((marker) => lowered.includes(marker));
}

function canonicalizeTeachingUrl(urlValue: string | null | undefined): string {
  const raw = String(urlValue || "").trim();
  if (!raw) return "";
  try {
    const parsed = new URL(raw);
    const params = new URLSearchParams(parsed.search);
    const filtered = new URLSearchParams();
    for (const [key, value] of params.entries()) {
      const lowered = key.toLowerCase();
      const isTrackingParam =
        lowered === "_gl"
        || lowered === "gclid"
        || lowered === "fbclid"
        || lowered.startsWith("utm_")
        || lowered === "_ga"
        || lowered.startsWith("_ga_");
      if (!isTrackingParam) {
        filtered.append(key, value);
      }
    }
    parsed.search = filtered.toString() ? `?${filtered.toString()}` : "";
    return parsed.toString();
  } catch {
    return raw;
  }
}

type TeachingReviewSummary = {
  workflowSummary?: string;
  totalSteps: number;
  confirmedSteps: number;
  unconfirmedSteps: number;
};

type TeachingExecutionReadiness = {
  runnable?: boolean;
  has_start_url?: boolean;
  start_url?: string | null;
  blocking_reasons?: string[];
  execution_warnings?: string[];
};

type GeneratedWorkflowSOP = {
  workflow_id: string;
  draft_id: string;
  workflow_name: string;
  readiness_status: "runnable" | "needs_more_teaching" | "manual_only";
  runnable: boolean;
  has_start_url: boolean;
  last_validated_date?: string | null;
  generated_at: string;
  markdown: string;
  source_summary?: {
    step_count?: number;
    captured_fields?: string[];
    captured_buttons?: string[];
    captured_pages?: string[];
    manual_step_count?: number;
    needs_confirmation_count?: number;
    workflow_summary_present?: boolean;
  };
};

type TeachingStepStatus = {
  label: "Runnable" | "Manual-only" | "Needs clarification";
  reason: string;
};

type EmployeeReadiness = {
  label: "Ready to test" | "Almost ready" | "Needs more teaching";
  reasons: string[];
  toneClass: string;
};

type ExtensionLearningReadiness = {
  label: string;
  reasons: string[];
  toneClass: string;
};

type TeachingStepCardProps = {
  step: WorkflowStep;
  stepNumber?: number;
  status: TeachingStepStatus;
  formatObservedAction: (action: BrowserAction) => string;
  compact?: boolean;
};

function TeachingStepCard({ step, stepNumber, status, formatObservedAction, compact = false }: TeachingStepCardProps) {
  const hasExtensionEvidence = step.observedActions.some((action) => action.source === "extension");
  const confidenceValue = Math.max(0, Math.min(1, step.billConfidence || 0));
  const confidenceLabel = confidenceValue >= 0.8 ? "high" : confidenceValue >= 0.5 ? "medium" : "low";
  const confidenceClass = confidenceValue >= 0.8
    ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-100"
    : confidenceValue >= 0.5
      ? "border-amber-400/40 bg-amber-500/10 text-amber-100"
      : "border-slate-500/50 bg-slate-800 text-slate-200";

  return (
    <article className={`rounded-xl border border-slate-700 bg-slate-950/70 text-sm ${compact ? "p-3" : "p-4"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {typeof stepNumber === "number" && (
              <span className="text-xs uppercase tracking-[0.16em] text-slate-500">Step {stepNumber}</span>
            )}
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${status.label === "Runnable" ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-200" : status.label === "Needs clarification" ? "border-amber-400/40 bg-amber-500/10 text-amber-100" : "border-slate-500/50 bg-slate-800 text-slate-200"}`}>
              {status.label}
            </span>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${step.confirmed ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-200" : "border-amber-400/40 bg-amber-500/10 text-amber-100"}`}>
              {step.confirmed ? "Confirmed" : "Unconfirmed"}
            </span>
            {hasExtensionEvidence && (
              <span className="rounded-full border border-cyan-400/40 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-semibold text-cyan-100">
                Source: Chrome extension
              </span>
            )}
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${confidenceClass}`}>
              Confidence: {confidenceLabel}
            </span>
          </div>
          <h3 className="mt-2 truncate font-semibold text-white">{step.title}</h3>
        </div>
      </div>

      <div className="mt-2 space-y-2">
        <p className="text-slate-300">{step.billSummary || "Bill is still summarizing this step."}</p>
        <div className="rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-2">
          <p className="text-[11px] uppercase tracking-[0.14em] text-cyan-200">Target</p>
          <p className="mt-1 text-xs text-cyan-50">{step.observedActions[0]?.label || step.observedActions[0]?.selector || "Not captured yet"}</p>
        </div>
      </div>

      <details className="mt-2 rounded-md border border-slate-800 bg-slate-900/60 px-3 py-2">
        <summary className="cursor-pointer text-[11px] uppercase tracking-[0.14em] text-slate-400">Show technical info</summary>
        <div className="mt-2 space-y-2 text-xs text-slate-300">
          <p>Confidence: {(confidenceValue * 100).toFixed(0)}%</p>
          <p>Employee explanation: {step.employeeExplanation || "Pending"}</p>
          <p>Required data: {step.requiredInputs.join(", ") || "Pending"}</p>
          <p>Decision rules: {step.decisionRules.join("; ") || "None yet"}</p>
          <p>Exceptions: {step.exceptions.join("; ") || "None yet"}</p>
          {step.pendingQuestion && <p>Pending question: {step.pendingQuestion}</p>}
          <div>
            <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">Observed browser actions</p>
            {step.observedActions.length === 0 ? (
              <p className="mt-1 text-slate-400">No browser actions captured yet.</p>
            ) : (
              <ul className="mt-1 space-y-1">
                {step.observedActions.map((action) => (
                  <li key={action.id}>{formatObservedAction(action)}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </details>
    </article>
  );
}

function summarizeExtensionEvent(event: Record<string, unknown> | null | undefined): string {
  if (!event) {
    return "No extension events yet";
  }
  return [
    String(event.event_type ?? "").trim(),
    String((event.target as Record<string, unknown> | undefined)?.target_label ?? "").trim(),
    String(event.current_url ?? "").trim(),
  ].filter(Boolean).join(" • ") || "Extension event captured";
}

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
  execution_readiness?: {
    executable?: boolean;
    runnable?: boolean;
    has_start_url?: boolean;
    start_url?: string | null;
    executable_action_count?: number;
    manual_action_count?: number;
    redacted_input_count?: number;
    blocking_reasons?: string[];
    warnings?: string[];
  };
  created_by_user_id?: string | null;
  created_by_name?: string | null;
  last_updated_by_user_id?: string | null;
  last_updated_by_name?: string | null;
  approved_by_user_id?: string | null;
  approved_by_name?: string | null;
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
  published_static_procedure?: boolean;
  created_by_user_id?: string | null;
  created_by_name?: string | null;
  last_updated_by_user_id?: string | null;
  last_updated_by_name?: string | null;
  approved_by_user_id?: string | null;
  approved_by_name?: string | null;
};

const STATIC_PROCEDURE_WORKFLOWS = new Set<string>(["smart_sherpa_sync", "marketplace_workflow"]);

function workflowSlug(value: string): string {
  return value.toLowerCase().replace(/\s+/g, "_");
}

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

type BillUserRole = "super_admin" | "admin" | "teacher" | "runner" | "viewer";

type BillUserRecord = {
  id: string;
  tenant_id?: string | null;
  email: string;
  name: string;
  role: BillUserRole;
  status: string;
  last_login_at?: string | null;
  created_at: string;
  updated_at: string;
};

type BillLoginResponse = {
  user: BillUserRecord;
  session_expires_at: string;
};

type BillCurrentUserResponse = {
  user: BillUserRecord;
};

type BillAuditLogRecord = {
  id: number;
  event_type: string;
  actor_user_name?: string | null;
  actor_role?: string | null;
  request_method?: string | null;
  request_path?: string | null;
  status_code?: number | null;
  created_at: string;
};

type KnowledgeRecord = {
  knowledge_id: string;
  title: string;
  category: string;
  applies_to: string[];
  content: string;
  source_type: "manual" | "document" | "imported" | "system";
  tags: string[];
  status: "active" | "draft" | "archived";
  created_by_user_id?: string | null;
  created_by_name?: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  tenant_id?: string | null;
};

type WorkerReleasePublicRecord = {
  id: string;
  version: string;
  upload_time: string;
  release_notes?: string | null;
  package_filename: string;
  package_sha256?: string | null;
  file_size_bytes?: number | null;
  status: string;
  released_by_name?: string | null;
  download_count: number;
};

type WorkerReleaseAdminRecord = WorkerReleasePublicRecord & {
  released_by_user_id?: string | null;
  channel: string;
};

type ExtensionReleasePublicRecord = {
  id: string;
  release_type: "chrome_extension";
  version_label: string;
  released_at: string;
  release_notes?: string | null;
  file_name: string;
  sha256_hash?: string | null;
  file_size_bytes?: number | null;
  status: string;
  released_by_name?: string | null;
  download_count: number;
};

type ExtensionReleaseAdminRecord = ExtensionReleasePublicRecord & {
  released_by_user_id?: string | null;
};

type WorkerDownloadUrlResponse = {
  release_id: string;
  version: string;
  package_filename: string;
  download_url: string;
  sha256?: string | null;
  expires_in_seconds?: number | null;
};

type ExtensionDownloadUrlResponse = {
  release_id: string;
  version_label: string;
  file_name: string;
  download_url: string;
  sha256_hash?: string | null;
  expires_in_seconds?: number | null;
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
const DEPRECATED_BACKEND_HOSTS = new Set(["api.bill-core.com", "core.bill-core.com"]);
const COMMAND_CENTER_VOICE_PREF_KEY = "bill.command-center.voice.enabled";
const COMMAND_CENTER_AUTO_SUBMIT_PREF_KEY = "bill.command-center.voice.autoSubmit.enabled";
const TEACHING_STARTUP_POLL_TIMEOUT_MS = 60000;
const TEACHING_STARTUP_MAX_POLL_ERRORS = 5;

const getConfiguredApiBase = (): string => {
  const configured = (process.env.NEXT_PUBLIC_API_BASE ?? "").trim();
  if (!configured) {
    return NEXT_PUBLIC_API_BASE_DEFAULT;
  }

  const sanitized = configured.replace(/\/$/, "");
  try {
    const hostname = new URL(sanitized).hostname.toLowerCase();
    if (DEPRECATED_BACKEND_HOSTS.has(hostname)) {
      console.warn(`[auth-proxy] Ignoring deprecated NEXT_PUBLIC_API_BASE=${sanitized}`);
      return NEXT_PUBLIC_API_BASE_DEFAULT;
    }
  } catch {
    // Ignore invalid override values and use the default.
    return NEXT_PUBLIC_API_BASE_DEFAULT;
  }

  return sanitized;
};

const getApiBase = (): string => {
  // Force all browser dashboard calls through the Next.js proxy so auth
  // header injection happens server-side for every request.
  if (typeof window !== "undefined") {
    console.log("[auth-proxy] using proxy path /api/proxy");
    return "/api/proxy";
  }
  const configured = getConfiguredApiBase();
  console.log(`[auth-proxy] server-side api base ${configured}`);
  return configured;
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

const shortEntityId = (id?: string | null): string => {
  if (!id) return "pending";
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
  const [currentUser, setCurrentUser] = useState<BillUserRecord | null>(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [authNotice, setAuthNotice] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [sessionExpiresAt, setSessionExpiresAt] = useState<string | null>(null);
  const [adminUsers, setAdminUsers] = useState<BillUserRecord[]>([]);
  const [adminAuditLogs, setAdminAuditLogs] = useState<BillAuditLogRecord[]>([]);
  const [knowledgeEntries, setKnowledgeEntries] = useState<KnowledgeRecord[]>([]);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [knowledgeError, setKnowledgeError] = useState<string | null>(null);
  const [knowledgeActionBusyKey, setKnowledgeActionBusyKey] = useState<string | null>(null);
  const [knowledgeActionFeedback, setKnowledgeActionFeedback] = useState<ActionFeedback | null>(null);
  const [adminBusy, setAdminBusy] = useState(false);
  const [adminError, setAdminError] = useState<string | null>(null);
  const [newUserName, setNewUserName] = useState("");
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  // Worker Download Center
  const [currentWorkerRelease, setCurrentWorkerRelease] = useState<WorkerReleasePublicRecord | null>(null);
  const [workerReleaseLoading, setWorkerReleaseLoading] = useState(false);
  const [workerReleaseError, setWorkerReleaseError] = useState<string | null>(null);
  const [workerDownloadBusy, setWorkerDownloadBusy] = useState(false);
  const [workerDownloadMessage, setWorkerDownloadMessage] = useState<string | null>(null);
  // Admin Worker Releases
  const [adminWorkerReleases, setAdminWorkerReleases] = useState<WorkerReleaseAdminRecord[]>([]);
  const [adminWorkerReleasesLoading, setAdminWorkerReleasesLoading] = useState(false);
  const [adminWorkerReleasesError, setAdminWorkerReleasesError] = useState<string | null>(null);
  const [newReleaseVersion, setNewReleaseVersion] = useState("");
  const [newReleaseFilename, setNewReleaseFilename] = useState("");
  const [newReleaseNotes, setNewReleaseNotes] = useState("");
  const [newReleaseChannel, setNewReleaseChannel] = useState("stable");
  // Extension Download Center
  const [currentExtensionRelease, setCurrentExtensionRelease] = useState<ExtensionReleasePublicRecord | null>(null);
  const [extensionReleaseLoading, setExtensionReleaseLoading] = useState(false);
  const [extensionReleaseError, setExtensionReleaseError] = useState<string | null>(null);
  const [extensionDownloadBusy, setExtensionDownloadBusy] = useState(false);
  const [extensionDownloadMessage, setExtensionDownloadMessage] = useState<string | null>(null);
  // Admin Extension Releases
  const [adminExtensionReleases, setAdminExtensionReleases] = useState<ExtensionReleaseAdminRecord[]>([]);
  const [adminExtensionReleasesLoading, setAdminExtensionReleasesLoading] = useState(false);
  const [adminExtensionReleasesError, setAdminExtensionReleasesError] = useState<string | null>(null);
  const [newExtensionVersionLabel, setNewExtensionVersionLabel] = useState("");
  const [newExtensionFilename, setNewExtensionFilename] = useState("");
  const [newExtensionReleaseNotes, setNewExtensionReleaseNotes] = useState("");
  const [newUserRole, setNewUserRole] = useState<BillUserRole>("viewer");
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
  const [guidedTeachingCopilotNotice, setGuidedTeachingCopilotNotice] = useState<string | null>(null);
  const [guidedTeachingCopilotInterpretation, setGuidedTeachingCopilotInterpretation] = useState<string | null>(null);
  const [guidedTeachingCopilotQuestion, setGuidedTeachingCopilotQuestion] = useState<string | null>(null);
  const [guidedTeachingInput, setGuidedTeachingInput] = useState("");
  const [guidedTeachingBusy, setGuidedTeachingBusy] = useState(false);
  const [guidedTeachingTargetStepId, setGuidedTeachingTargetStepId] = useState<string | null>(null);
  const [guidedTeachingReviewSummary, setGuidedTeachingReviewSummary] = useState<TeachingReviewSummary | null>(null);
  const [guidedTeachingExecutionReadiness, setGuidedTeachingExecutionReadiness] = useState<TeachingExecutionReadiness | null>(null);
  const [guidedTeachingWarnings, setGuidedTeachingWarnings] = useState<string[]>([]);
  const [guidedTeachingApprovalMessage, setGuidedTeachingApprovalMessage] = useState<string | null>(null);
  const [guidedTeachingRunNowBusy, setGuidedTeachingRunNowBusy] = useState(false);
  const [guidedTeachingRunNowMessage, setGuidedTeachingRunNowMessage] = useState<string | null>(null);
  const [guidedTeachingSopBusy, setGuidedTeachingSopBusy] = useState(false);
  const [guidedTeachingSopError, setGuidedTeachingSopError] = useState<string | null>(null);
  const [guidedTeachingSopRecord, setGuidedTeachingSopRecord] = useState<GeneratedWorkflowSOP | null>(null);
  const [editingStepId, setEditingStepId] = useState<string | null>(null);
  const [editingAdvancedDetailsOpen, setEditingAdvancedDetailsOpen] = useState(false);
  const [editingStepState, setEditingStepState] = useState<GuidedStepEditState>({
    title: "",
    employeeExplanation: "",
    billSummary: "",
    decisionRules: "",
    exceptions: "",
    requiredInputs: "",
  });
  const [teachingVoiceError, setTeachingVoiceError] = useState<string | null>(null);
  // Teaching startup state — tracks browser_opening → active/failed
  const [teachingStartupState, setTeachingStartupState] = useState<TeachingStartupState | null>(null);
  const [extensionLearningSessionId, setExtensionLearningSessionId] = useState<string>("");
  const [extensionLearningState, setExtensionLearningState] = useState<TeachingStartupState | null>(null);
  const extensionLearningBootstrapRef = useRef(false);
  const teachingStartupPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const teachingStartupTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const teachingStartupPollErrorCountRef = useRef<number>(0);
  const extensionLearningPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const extensionLearningPollErrorCountRef = useRef<number>(0);
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

  const stopExtensionLearningPoll = useCallback(() => {
    if (extensionLearningPollRef.current !== null) {
      clearInterval(extensionLearningPollRef.current);
      extensionLearningPollRef.current = null;
    }
    extensionLearningPollErrorCountRef.current = 0;
  }, []);

  const startExtensionLearningPoll = useCallback(
    (sessionId: string) => {
      stopExtensionLearningPoll();
      const apiBase = getApiBase();
      const trimmedSessionId = String(sessionId || "").trim();
      if (!apiBase || !trimmedSessionId) return;

      extensionLearningPollErrorCountRef.current = 0;
      setExtensionLearningSessionId(trimmedSessionId);

      const fetchExtensionLearningState = async () => {
        try {
          const res = await fetch(`${apiBase}/api/teaching/session/${trimmedSessionId}/status`);
          if (!res.ok) {
            extensionLearningPollErrorCountRef.current += 1;
            if (extensionLearningPollErrorCountRef.current >= TEACHING_STARTUP_MAX_POLL_ERRORS) {
              stopExtensionLearningPoll();
            }
            return;
          }
          extensionLearningPollErrorCountRef.current = 0;
          const data = normalizeTeachingStatus((await res.json()) as TeachingStartupState);
          setExtensionLearningState(data);
          if (data.teaching_session) {
            setGuidedTeachingFromSession(mapApiTeachingSession(data.teaching_session));
          }
          if (data.status === "failed") {
            stopExtensionLearningPoll();
          }
        } catch {
          extensionLearningPollErrorCountRef.current += 1;
          if (extensionLearningPollErrorCountRef.current >= TEACHING_STARTUP_MAX_POLL_ERRORS) {
            stopExtensionLearningPoll();
          }
        }
      };

      void fetchExtensionLearningState();
      extensionLearningPollRef.current = setInterval(() => {
        void fetchExtensionLearningState();
      }, 2000);
    },
    [stopExtensionLearningPoll],
  );


  useEffect(() => {
    if (extensionLearningBootstrapRef.current) return;
    extensionLearningBootstrapRef.current = true;

    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("extension_session_id")?.trim() || params.get("teaching_session_id")?.trim() || "";
    if (sessionId) {
      void startExtensionLearningPoll(sessionId);
    }
  }, [startExtensionLearningPoll]);
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
          draft_id: current?.draft_id ?? null,
          workflow_name: current?.workflow_name ?? "Workflow",
          target_machine_uuid: current?.target_machine_uuid ?? null,
          target_machine_name: current?.target_machine_name ?? null,
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
          const data = normalizeTeachingStatus((await res.json()) as TeachingStartupState);
          logTeachOverlay("startup status poll", {
            session_id: sessionId,
            status: data.status,
            task_id: data.task_id ?? null,
            message: data.message ?? "",
          });
          if (data.status === "active") {
            if (teachingStartupTimeoutRef.current !== null) {
              clearTimeout(teachingStartupTimeoutRef.current);
              teachingStartupTimeoutRef.current = null;
            }
            console.log("[teaching-browser] active callback received", {
              session_id: sessionId,
              workflow_name: data.workflow_name,
            });
            if (data.draft_id) {
              setTeachingSessionDraftId(data.draft_id);
            }
          }
          setTeachingStartupState(data);
          if (data.teaching_session) {
            setGuidedTeachingFromSession(mapApiTeachingSession(data.teaching_session));
          }
          if (data.copilot_notice !== undefined) {
            setGuidedTeachingCopilotNotice(data.copilot_notice ?? null);
          }
          if (data.copilot_interpretation !== undefined) {
            setGuidedTeachingCopilotInterpretation(data.copilot_interpretation ?? null);
          }
          if (data.copilot_question !== undefined) {
            setGuidedTeachingCopilotQuestion(data.copilot_question ?? null);
          }
          if (data.status === "failed") {
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
  useEffect(() => () => {
    stopTeachingStartupPoll();
    stopExtensionLearningPoll();
  }, [stopExtensionLearningPoll, stopTeachingStartupPoll]);

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
    (input: TeachingSessionApiResponse["teaching_session"]): TeachingSession => {
      const mappedSnapshot = input.page_context_snapshot
        ? {
            url: input.page_context_snapshot.url,
            title: input.page_context_snapshot.title,
            domain: input.page_context_snapshot.domain,
            visible_buttons: input.page_context_snapshot.visible_buttons,
            visible_inputs: input.page_context_snapshot.visible_inputs,
            visible_links: input.page_context_snapshot.visible_links,
            visible_headings: input.page_context_snapshot.visible_headings,
            buttons: input.page_context_snapshot.buttons,
            inputs: input.page_context_snapshot.inputs,
            links: input.page_context_snapshot.links,
            headings: input.page_context_snapshot.headings,
            active_element: input.page_context_snapshot.active_element,
            recent_click_label: input.page_context_snapshot.recent_click_label,
            recent_type_field: input.page_context_snapshot.recent_type_field,
            modal_present: input.page_context_snapshot.modal_present,
            modal_title: input.page_context_snapshot.modal_title,
            captured_at: input.page_context_snapshot.captured_at,
          }
        : null;

      const safeSnapshot = isInvalidTeachingContextSnapshot(mappedSnapshot)
        ? (() => {
            console.warn("TEACH_UI_INVALID_CONTEXT_MASKED", {
              session_id: input.session_id,
              url: mappedSnapshot?.url || "",
              title: mappedSnapshot?.title || "",
              domain: mappedSnapshot?.domain || "",
            });
            return {
              url: "",
              title: INVALID_TEACHING_CONTEXT_MESSAGE,
              domain: "",
              visible_buttons: [],
              visible_inputs: [],
              visible_links: [],
              visible_headings: [],
              buttons: [],
              inputs: [],
              links: [],
              headings: [],
              active_element: null,
              recent_click_label: null,
              recent_type_field: null,
              modal_present: false,
              modal_title: null,
              captured_at: mappedSnapshot?.captured_at,
            };
          })()
        : mappedSnapshot;

      return {
        sessionId: input.session_id,
        workflowName: input.workflow_name,
        workflowSummary: input.workflow_summary ?? undefined,
        status: input.status,
        startUrl: input.start_url ?? undefined,
        observedStartUrl: input.observed_start_url ?? undefined,
        suggestedStartUrl: input.suggested_start_url ?? undefined,
        observedCurrentPage: input.observed_current_page ?? undefined,
        pageContextSnapshot: safeSnapshot,
        extensionConnectionStatus: input.extension_connection_status ?? null,
        extensionEventCount: Number(input.extension_event_count ?? 0),
        lastExtensionEvent: input.last_extension_event ?? null,
        extensionEvents: (input.extension_events ?? []) as Record<string, unknown>[],
      steps: (input.steps ?? []).map((step) => ({
        id: step.id,
        order: step.order,
        title: step.title,
        observedActions: (step.observed_actions ?? []).map((action) => ({
          id: action.id,
          type: action.type,
          source: action.source ?? undefined,
          selector: action.selector ?? undefined,
          selectors: action.selectors ?? undefined,
          label: action.label ?? undefined,
          target_label: action.target_label ?? undefined,
          target_type: action.target_type ?? undefined,
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
      };
    },
    [],
  );

  const normalizeTeachingStatus = useCallback((status: TeachingStartupState): TeachingStartupState => {
    const nested = status.teaching_session;
    const normalizedSession: TeachingSessionApiResponse["teaching_session"] = {
      session_id: nested?.session_id ?? status.session_id,
      workflow_name: nested?.workflow_name ?? status.workflow_name,
      workflow_summary: nested?.workflow_summary ?? null,
      status: nested?.status ?? "teaching",
      start_url: nested?.start_url ?? status.start_url ?? null,
      observed_start_url: nested?.observed_start_url ?? null,
      suggested_start_url: nested?.suggested_start_url ?? status.suggested_start_url ?? null,
      observed_current_page: nested?.observed_current_page ?? status.observed_current_page ?? null,
      extension_connection_status: nested?.extension_connection_status ?? status.extension_connection_status ?? null,
      extension_event_count: nested?.extension_event_count ?? status.extension_event_count ?? 0,
      last_extension_event: nested?.last_extension_event ?? status.latest_extension_event ?? null,
      extension_events: nested?.extension_events ?? [],
      page_context_snapshot: nested?.page_context_snapshot ?? status.page_context_snapshot ?? null,
      steps: nested?.steps ?? status.steps ?? [],
    };

    return {
      ...status,
      teaching_session: normalizedSession,
    };
  }, []);

  const applyGuidedTeachingApiResponse = useCallback(
    (body: TeachingSessionApiResponse) => {
      setGuidedTeachingSession(mapApiTeachingSession(body.teaching_session));
      setGuidedTeachingCopilotNotice(body.copilot_notice ?? null);
      setGuidedTeachingCopilotInterpretation(body.copilot_interpretation ?? null);
      setGuidedTeachingCopilotQuestion(body.copilot_question ?? null);
      setGuidedTeachingWarnings(body.warnings ?? []);
      setGuidedTeachingExecutionReadiness(body.execution_readiness ?? null);
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
      setGuidedTeachingExecutionReadiness(null);
      setGuidedTeachingWarnings([]);
      setGuidedTeachingApprovalMessage(null);
      setGuidedTeachingRunNowMessage(null);
      setGuidedTeachingSopError(null);
      setGuidedTeachingSopRecord(null);
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
    const sourcePrefix = action.source === "extension" ? "Extension observed" : action.source === "manual" ? "Manual note" : "Bill saw";
    if (action.type === "navigate") {
      try {
        const parsed = action.url ? new URL(action.url) : null;
        const path = parsed ? `${parsed.hostname}${parsed.pathname || "/"}` : action.url || "page";
        return `${sourcePrefix}: navigated to ${path}`;
      } catch {
        return `${sourcePrefix}: navigated to ${action.url || "page"}`;
      }
    }
    if (action.type === "type") {
      return `${sourcePrefix}: typed into ${action.target_label || action.label || "field"}`;
    }
    if (action.type === "select") {
      return `${sourcePrefix}: selected option in ${action.target_label || action.label || "field"}`;
    }
    if (action.type === "submit") {
      return `${sourcePrefix}: submitted ${action.target_label || action.label || "form"}`;
    }
    if (action.type === "focus") {
      return `${sourcePrefix}: focused ${action.target_label || action.label || "field"}`;
    }
    return `${sourcePrefix}: clicked ${action.target_label || action.label || "element"}`;
  }, []);

  const setGuidedTeachingFromSession = useCallback((session: TeachingSession) => {
    setGuidedTeachingSession(session);
    setGuidedTeachingWarnings([]);
    setGuidedTeachingExecutionReadiness(null);
    setGuidedTeachingSopError(null);
    setGuidedTeachingSopRecord(null);
    setGuidedTeachingReviewSummary({
      workflowSummary: session.workflowSummary,
      totalSteps: session.steps.length,
      confirmedSteps: session.steps.filter((step) => step.confirmed).length,
      unconfirmedSteps: session.steps.filter((step) => !step.confirmed).length,
    });
  }, []);

  const estimateTeachingExecutionReadiness = useCallback((session: TeachingSession): TeachingExecutionReadiness => {
    const blockingReasons: string[] = [];
    const executionWarnings: string[] = [];
    const allActions = session.steps.flatMap((step) => step.observedActions ?? []);
    const confirmedStartUrl = canonicalizeTeachingUrl(session.startUrl);
    const hasStartUrl = Boolean(confirmedStartUrl);
    const hasRunnableInteractiveAction = allActions.some((action) => {
      if (action.type === "navigate") {
        return Boolean(action.url?.trim());
      }
      if (action.type === "click" || action.type === "submit" || action.type === "focus" || action.type === "type") {
        return Boolean(action.selector?.trim());
      }
      return false;
    });

    if (session.steps.length === 0) {
      blockingReasons.push("No steps were captured yet.");
    }

    if (allActions.length === 0) {
      blockingReasons.push("Workflow is manual-only and needs more teaching before it can run.");
    }

    if (!hasStartUrl) {
      blockingReasons.push("No starting page was captured.");
    }

    const hasManualOnlyStep = session.steps.some((step) => step.observedActions.length === 0);
    if (hasManualOnlyStep) {
      executionWarnings.push("At least one step is manual-only and may require a person during execution.");
    }

    const hasRedactedInput = allActions.some((action) => Boolean(action.valueRedacted));
    if (hasRedactedInput) {
      executionWarnings.push("At least one input is redacted and will require a person to enter data during the run.");
    }

    const hasUnconfirmedSteps = session.steps.some((step) => !step.confirmed);
    if (hasUnconfirmedSteps) {
      executionWarnings.push("Some steps are still unconfirmed.");
    }

    return {
      runnable: blockingReasons.length === 0 && Boolean(hasStartUrl || hasRunnableInteractiveAction),
      has_start_url: hasStartUrl,
      start_url: confirmedStartUrl || null,
      blocking_reasons: blockingReasons,
      execution_warnings: executionWarnings,
    };
  }, []);

  const localTeachingExecutionReadiness = useMemo(() => {
    if (!guidedTeachingSession) return null;
    return estimateTeachingExecutionReadiness(guidedTeachingSession);
  }, [estimateTeachingExecutionReadiness, guidedTeachingSession]);

  const guidedTeachingEffectiveReadiness = useMemo(() => {
    if (!localTeachingExecutionReadiness && !guidedTeachingExecutionReadiness) return null;
    if (!guidedTeachingExecutionReadiness) return localTeachingExecutionReadiness;
    if (!localTeachingExecutionReadiness) return guidedTeachingExecutionReadiness;

    const mergedBlockingReasons = Array.from(
      new Set([
        ...(guidedTeachingExecutionReadiness.blocking_reasons ?? []),
        ...(localTeachingExecutionReadiness.blocking_reasons ?? []),
      ]),
    );
    const mergedExecutionWarnings = Array.from(
      new Set([
        ...(guidedTeachingExecutionReadiness.execution_warnings ?? []),
        ...(localTeachingExecutionReadiness.execution_warnings ?? []),
      ]),
    );

    return {
      ...localTeachingExecutionReadiness,
      ...guidedTeachingExecutionReadiness,
      runnable:
        guidedTeachingExecutionReadiness.runnable !== undefined
          ? Boolean(guidedTeachingExecutionReadiness.runnable)
          : Boolean(localTeachingExecutionReadiness.runnable),
      has_start_url:
        guidedTeachingExecutionReadiness.has_start_url !== undefined
          ? Boolean(guidedTeachingExecutionReadiness.has_start_url)
          : Boolean(localTeachingExecutionReadiness.has_start_url),
      start_url: guidedTeachingExecutionReadiness.start_url ?? localTeachingExecutionReadiness.start_url ?? null,
      blocking_reasons: mergedBlockingReasons,
      execution_warnings: mergedExecutionWarnings,
    } satisfies TeachingExecutionReadiness;
  }, [guidedTeachingExecutionReadiness, localTeachingExecutionReadiness]);

  const explainStepStatus = useCallback((step: WorkflowStep): TeachingStepStatus => {
    const actions = step.observedActions ?? [];
    if (actions.length === 0) {
      return {
        label: "Manual-only",
        reason: "Bill only has a note. He does not know what to click yet.",
      };
    }

    let hasRunnable = false;
    let hasManualConstraint = false;
    let hasAmbiguity = false;

    for (const action of actions) {
      if (action.type === "navigate") {
        if ((action.url ?? "").trim()) {
          hasRunnable = true;
        } else {
          hasManualConstraint = true;
        }
        continue;
      }

      if (action.type === "click" || action.type === "submit" || action.type === "focus") {
        if ((action.selector ?? "").trim()) {
          hasRunnable = true;
        } else if ((action.label ?? "").trim()) {
          hasAmbiguity = true;
        } else {
          hasManualConstraint = true;
        }
        continue;
      }

      if (action.type === "type") {
        if ((action.selector ?? "").trim()) {
          hasRunnable = true;
        } else if ((action.label ?? "").trim()) {
          hasAmbiguity = true;
        } else {
          hasManualConstraint = true;
        }
        continue;
      }

      if (action.type === "select") {
        if ((action.selector ?? "").trim() && !action.valueRedacted) {
          hasRunnable = true;
        } else if (action.valueRedacted) {
          hasManualConstraint = true;
        } else {
          hasAmbiguity = true;
        }
        continue;
      }
    }

    if (hasRunnable && !hasManualConstraint && !hasAmbiguity) {
      return {
        label: "Runnable",
        reason: "Bill has a replayable click/type target for this step.",
      };
    }

    if (hasRunnable && (hasManualConstraint || hasAmbiguity)) {
      return {
        label: "Needs clarification",
        reason: "Bill captured part of this step, but one action still needs a clearer target.",
      };
    }

    if (hasAmbiguity) {
      return {
        label: "Needs clarification",
        reason: "Bill found multiple possible targets. Confirm the exact button or field.",
      };
    }

    return {
      label: "Manual-only",
      reason: "Bill saw the action, but it was saved as a note, not a runnable step.",
    };
  }, []);

  const canonicalStartUrl = useMemo(() => {
    if (!guidedTeachingSession) return "";
    const fromReadiness = String(guidedTeachingEffectiveReadiness?.start_url || "").trim();
    if (fromReadiness) return fromReadiness;
    const fromSession = canonicalizeTeachingUrl(guidedTeachingSession.startUrl);
    if (fromSession) return fromSession;
    return "";
  }, [guidedTeachingEffectiveReadiness?.start_url, guidedTeachingSession]);

  const suggestedStartUrl = useMemo(() => {
    if (!guidedTeachingSession) return "";
    const explicitSuggestion = canonicalizeTeachingUrl(guidedTeachingSession.suggestedStartUrl);
    if (explicitSuggestion) return explicitSuggestion;
    const fromSnapshot = canonicalizeTeachingUrl(guidedTeachingSession.pageContextSnapshot?.url);
    if (fromSnapshot && fromSnapshot !== canonicalStartUrl) return fromSnapshot;
    return "";
  }, [canonicalStartUrl, guidedTeachingSession]);

  const observedCurrentPage = useMemo(() => {
    const fromSession = String(guidedTeachingSession?.observedCurrentPage || "").trim();
    if (fromSession) return fromSession;
    const snapshot = guidedTeachingSession?.pageContextSnapshot;
    return String(snapshot?.url || snapshot?.domain || "").trim();
  }, [guidedTeachingSession]);

  const capturedButtons = useMemo(() => {
    const snapshot = guidedTeachingSession?.pageContextSnapshot;
    const visible = (snapshot?.visible_buttons ?? [])
      .map((button) => String(button.text || button.aria_label || "").trim())
      .filter(Boolean);
    const fallback = (snapshot?.buttons ?? []).map((value) => String(value || "").trim()).filter(Boolean);
    return Array.from(new Set([...(visible.length ? visible : fallback)])).slice(0, 8);
  }, [guidedTeachingSession?.pageContextSnapshot]);

  const capturedFields = useMemo(() => {
    const snapshot = guidedTeachingSession?.pageContextSnapshot;
    const visible = (snapshot?.visible_inputs ?? [])
      .map((input) => String(input.label || input.placeholder || input.name || "").trim())
      .filter(Boolean);
    const fallback = (snapshot?.inputs ?? [])
      .map((input) => String(input.label || input.placeholder || "").trim())
      .filter(Boolean);
    return Array.from(new Set([...(visible.length ? visible : fallback)])).slice(0, 8);
  }, [guidedTeachingSession?.pageContextSnapshot]);

  const capturedLinks = useMemo(() => {
    const snapshot = guidedTeachingSession?.pageContextSnapshot;
    const visible = (snapshot?.visible_links ?? [])
      .map((link) => String(link.text || link.href || "").trim())
      .filter(Boolean);
    const fallback = (snapshot?.links ?? []).map((value) => String(value || "").trim()).filter(Boolean);
    return Array.from(new Set([...(visible.length ? visible : fallback)])).slice(0, 8);
  }, [guidedTeachingSession?.pageContextSnapshot]);

  const stepStatusSummary = useMemo(() => {
    const steps = guidedTeachingSession?.steps ?? [];
    let runnable = 0;
    let manualOnly = 0;
    let needsClarification = 0;
    for (const step of steps) {
      const status = explainStepStatus(step);
      if (status.label === "Runnable") runnable += 1;
      if (status.label === "Manual-only") manualOnly += 1;
      if (status.label === "Needs clarification") needsClarification += 1;
    }
    return { runnable, manualOnly, needsClarification, total: steps.length };
  }, [explainStepStatus, guidedTeachingSession?.steps]);

  const teachingObservedActionCount = useMemo(() => {
    return (guidedTeachingSession?.steps ?? []).reduce(
      (count, step) => count + (step.observedActions?.length ?? 0),
      0,
    );
  }, [guidedTeachingSession?.steps]);

  const teachingExecutableActionCount = useMemo(() => {
    const executableTypes = new Set(["click", "type", "select", "submit", "navigate"]);
    return (guidedTeachingSession?.steps ?? []).reduce((count, step) => {
      const stepCount = (step.observedActions ?? []).filter((action) => {
        const source = String(action.source || "browser").toLowerCase();
        if (source !== "browser") return false;
        return executableTypes.has(String(action.type || "").toLowerCase());
      }).length;
      return count + stepCount;
    }, 0);
  }, [guidedTeachingSession?.steps]);

  const teachingCaptureReady = teachingExecutableActionCount > 0;

  const lastCapturedActionSummary = useMemo(() => {
    const allActions = (guidedTeachingSession?.steps ?? [])
      .flatMap((step) => step.observedActions ?? [])
      .filter((action) => Boolean(action.timestamp));
    if (!allActions.length) return "No actions captured yet";
    const latest = [...allActions].sort((a, b) => {
      const left = Date.parse(a.timestamp || "") || 0;
      const right = Date.parse(b.timestamp || "") || 0;
      return right - left;
    })[0];
    return formatObservedAction(latest);
  }, [formatObservedAction, guidedTeachingSession?.steps]);

  const extensionLearningSession = useMemo(() => {
    if (!extensionLearningState?.teaching_session) return null;
    return mapApiTeachingSession(extensionLearningState.teaching_session);
  }, [extensionLearningState, mapApiTeachingSession]);

  const extensionLearningStepStatusSummary = useMemo(() => {
    const steps = extensionLearningSession?.steps ?? [];
    let runnable = 0;
    let manualOnly = 0;
    let needsClarification = 0;
    for (const step of steps) {
      const status = explainStepStatus(step);
      if (status.label === "Runnable") runnable += 1;
      if (status.label === "Manual-only") manualOnly += 1;
      if (status.label === "Needs clarification") needsClarification += 1;
    }
    return { runnable, manualOnly, needsClarification, total: steps.length };
  }, [explainStepStatus, extensionLearningSession?.steps]);

  const extensionLearningReadiness = useMemo(() => {
    if (!extensionLearningSession) return null;
    const hasStart = Boolean(extensionLearningSession.pageContextSnapshot?.url || extensionLearningSession.pageContextSnapshot?.domain);
    const hasExtensionEvents = (extensionLearningSession.extensionEventCount ?? 0) > 0;
    const hasRunnableStep = extensionLearningStepStatusSummary.runnable > 0;
    const reasons: string[] = [];

    if (!hasExtensionEvents) {
      reasons.push("Waiting for extension events.");
    }
    if (!hasStart) {
      reasons.push("Waiting for a captured page context.");
    }
    if (!hasRunnableStep) {
      reasons.push("Bill needs at least one runnable step before testing.");
    }

    return {
      label: hasRunnableStep && hasStart ? "Ready to test" : "Still learning",
      reasons,
      toneClass: hasRunnableStep && hasStart ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-100" : "border-amber-400/40 bg-amber-500/10 text-amber-100",
    } satisfies ExtensionLearningReadiness;
  }, [extensionLearningSession, extensionLearningStepStatusSummary]);

  const isAdminUser = currentUser?.role === "admin" || currentUser?.role === "super_admin";
  const extensionLearningVisible = Boolean(extensionLearningSessionId.trim() || extensionLearningSession || extensionLearningState);
  const extensionLearningWorkerStatus = onlineWorkers.length > 0 ? "online" : "offline or unavailable";
  const extensionLearningConnectionStatus = extensionLearningSession?.extensionConnectionStatus
    ?? (extensionLearningSession?.extensionEventCount ? "watching" : "not paired");
  const extensionLearningLatestEvent = (extensionLearningSession?.lastExtensionEvent
    ?? extensionLearningSession?.pageContextSnapshot?.last_extension_event
    ?? null) as Record<string, unknown> | null;

  const employeeReadiness = useMemo((): EmployeeReadiness => {
    const readiness = guidedTeachingEffectiveReadiness;
    const reasons: string[] = [];
    const hasStart = Boolean(readiness?.has_start_url || canonicalStartUrl);
    const hasRunnableStep = stepStatusSummary.runnable > 0;
    const hasBrowserContext = teachingObservedActionCount > 0;

    if (readiness?.runnable) {
      reasons.push("Bill has a starting page and at least one runnable step.");
      if (stepStatusSummary.manualOnly > 0) {
        reasons.push("Some steps are still notes only, but you can test the core path now.");
      }
      return {
        label: "Ready to test",
        reasons,
        toneClass: "border-emerald-400/40 bg-emerald-500/10 text-emerald-100",
      };
    }

    if (!hasStart) {
      reasons.push("Bill still needs a starting page.");
    }
    if (!hasRunnableStep) {
      if (hasStart && hasBrowserContext) {
        reasons.push("Bill sees the page. Click a button or field to create the first step.");
      }
      reasons.push("Bill needs at least one runnable step before testing.");
    }
    if ((readiness?.blocking_reasons ?? []).length > 0) {
      reasons.push(...(readiness?.blocking_reasons ?? []).slice(0, 2));
    }

    if (hasStart || hasRunnableStep) {
      return {
        label: "Almost ready",
        reasons,
        toneClass: "border-amber-400/40 bg-amber-500/10 text-amber-100",
      };
    }

    return {
      label: "Needs more teaching",
      reasons,
      toneClass: "border-rose-400/40 bg-rose-500/10 text-rose-100",
    };
  }, [canonicalStartUrl, guidedTeachingEffectiveReadiness, stepStatusSummary.manualOnly, stepStatusSummary.runnable, teachingObservedActionCount]);

  const teachingCoach = useMemo(() => {
    const session = guidedTeachingSession;
    const hasPurpose = Boolean(session?.workflowSummary?.trim());
    const hasStart = Boolean(canonicalStartUrl);
    const hasSnapshot = Boolean(session?.pageContextSnapshot?.url || session?.pageContextSnapshot?.domain);
    const hasBrowserContext = teachingObservedActionCount > 0;
    const latestStep =
      !session || session.steps.length === 0
        ? null
        : ([...session.steps].reverse().find((step) => !step.confirmed)
          ?? session.steps[session.steps.length - 1]
          ?? null);
    const latestStatus = latestStep ? explainStepStatus(latestStep) : null;

    if (!hasPurpose) {
      return {
        phase: "Define workflow purpose",
        guidance:
          "Tell Bill what this workflow is for, like: 'This logs into TrackVia and opens the client search page.'",
        nextAction: "Describe the workflow in one sentence.",
        examplePhrase: "This workflow logs into TrackVia and opens the client search page.",
      };
    }
    if (!hasStart) {
      return {
        phase: "Choose starting page",
        guidance: "Now give Bill the starting URL or open the page in the teaching browser.",
        nextAction: "Open the login page or paste the starting URL.",
        examplePhrase: "Open TrackVia's login page.",
      };
    }
    if (!hasSnapshot || isInvalidTeachingContextSnapshot(session?.pageContextSnapshot)) {
      return {
        phase: "Confirm Bill sees the page",
        guidance: "Make sure the real webpage tab is active so Bill can read fields and buttons.",
        nextAction: "Switch to the real browser tab.",
        examplePhrase: "Bill should be able to see the login form now.",
      };
    }
    if ((session?.steps.length ?? 0) === 0) {
      return {
        phase: "Teach first action",
        guidance: hasBrowserContext
          ? "Bill sees the page. Click a button or field to create the first step."
          : "Bill sees the page. Tell Bill what to click or type next.",
        nextAction: "Capture the first click or field entry.",
        examplePhrase: "Click the Sign In button.",
      };
    }
    if (latestStep && !latestStep.confirmed) {
      return {
        phase: "Confirm runnable step",
        guidance:
          latestStatus?.label === "Runnable"
            ? "Review this step. If it looks right, confirm it."
            : "This step needs clarification. Add detail so Bill knows the exact target.",
        nextAction: latestStatus?.label === "Runnable" ? "Confirm the current step." : "Fix the target or add one more clue.",
        examplePhrase: latestStatus?.label === "Runnable" ? "Yes, confirm this step." : "Click the blue Sign In button.",
      };
    }
    if (!guidedTeachingEffectiveReadiness?.runnable) {
      return {
        phase: "Continue or finish",
        guidance: "Keep teaching the next action or finish once Bill has a runnable path.",
        nextAction: "Teach the next missing action.",
        examplePhrase: "After login, open the client search page.",
      };
    }
    return {
      phase: "Ready to test",
      guidance: "Bill has enough to run. Start a test run and confirm the result.",
      nextAction: "Run the workflow and verify the result.",
      examplePhrase: "Run a test on this taught workflow.",
    };
  }, [canonicalStartUrl, explainStepStatus, guidedTeachingEffectiveReadiness?.runnable, guidedTeachingSession, teachingObservedActionCount]);

  const getLatestRelevantStep = useCallback((): WorkflowStep | null => {
    if (!guidedTeachingSession || guidedTeachingSession.steps.length === 0) {
      return null;
    }
    const latestUnconfirmed = [...guidedTeachingSession.steps].reverse().find((step) => !step.confirmed);
    return latestUnconfirmed ?? guidedTeachingSession.steps[guidedTeachingSession.steps.length - 1] ?? null;
  }, [guidedTeachingSession]);

  const latestTeachingStep = useMemo(() => getLatestRelevantStep(), [getLatestRelevantStep]);

  const callTeachingStepEndpoint = useCallback(async (
    stepId: string,
    method: "PATCH" | "DELETE" | "POST",
    suffix = "",
    payload?: Record<string, unknown>,
  ) => {
    if (!guidedTeachingSession) {
      return;
    }
    const apiBase = getApiBase();
    if (!apiBase) {
      throw new Error("NEXT_PUBLIC_API_BASE is not set");
    }
    const response = await fetch(
      `${apiBase}/api/teaching/session/${guidedTeachingSession.sessionId}/steps/${stepId}${suffix}`,
      {
        method,
        headers: payload ? { "Content-Type": "application/json" } : undefined,
        body: payload ? JSON.stringify(payload) : undefined,
      },
    );
    const body = (await response.json()) as { detail?: string; teaching_session?: TeachingSessionApiResponse["teaching_session"] };
    if (!response.ok) {
      throw new Error(body.detail ?? `Step correction failed (${response.status})`);
    }
    if (body.teaching_session) {
      setGuidedTeachingFromSession(mapApiTeachingSession(body.teaching_session));
    }
  }, [guidedTeachingSession, mapApiTeachingSession, setGuidedTeachingFromSession]);

  const handleEditStep = useCallback((step: WorkflowStep) => {
    setEditingStepId(step.id);
    setEditingAdvancedDetailsOpen(false);
    setEditingStepState({
      title: step.title,
      employeeExplanation: step.employeeExplanation ?? "",
      billSummary: step.billSummary,
      decisionRules: step.decisionRules.join("; "),
      exceptions: step.exceptions.join("; "),
      requiredInputs: step.requiredInputs.join(", "),
    });
  }, []);

  const handleCancelEditStep = useCallback(() => {
    setEditingStepId(null);
  }, []);

  const handleSaveEditStep = useCallback(async (stepId: string) => {
    if (!guidedTeachingSession || guidedTeachingBusy) return;
    setGuidedTeachingBusy(true);
    try {
      await callTeachingStepEndpoint(stepId, "PATCH", "", {
        title: editingStepState.title,
        employee_explanation: editingStepState.employeeExplanation,
        bill_summary: editingStepState.billSummary,
        decision_rules: editingStepState.decisionRules.split(";").map((value) => value.trim()).filter(Boolean),
        exceptions: editingStepState.exceptions.split(";").map((value) => value.trim()).filter(Boolean),
        required_inputs: editingStepState.requiredInputs.split(",").map((value) => value.trim()).filter(Boolean),
      });
      setEditingStepId(null);
      setGuidedTeachingMessages((current) => [...current, { role: "assistant", message: "I updated that step." }]);
    } catch (error) {
      setGuidedTeachingMessages((current) => [
        ...current,
        {
          role: "assistant",
          message: `I couldn't save those edits: ${error instanceof Error ? error.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setGuidedTeachingBusy(false);
    }
  }, [callTeachingStepEndpoint, editingStepState, guidedTeachingBusy, guidedTeachingSession]);

  const handleDeleteStep = useCallback(async (step: WorkflowStep, assistantMessage = "No problem, I removed that step.") => {
    if (!guidedTeachingSession || guidedTeachingBusy) return;
    setGuidedTeachingBusy(true);
    try {
      await callTeachingStepEndpoint(step.id, "DELETE");
      setGuidedTeachingMessages((current) => [...current, { role: "assistant", message: assistantMessage }]);
      if (guidedTeachingTargetStepId === step.id) {
        setGuidedTeachingTargetStepId(null);
      }
    } catch (error) {
      setGuidedTeachingMessages((current) => [
        ...current,
        {
          role: "assistant",
          message: `I couldn't remove that step: ${error instanceof Error ? error.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setGuidedTeachingBusy(false);
    }
  }, [callTeachingStepEndpoint, guidedTeachingBusy, guidedTeachingSession, guidedTeachingTargetStepId]);

  const handleNotImportant = useCallback(async (step: WorkflowStep) => {
    await handleDeleteStep(step, "No problem, I removed that step.");
  }, [handleDeleteStep]);

  const handleRedoStep = useCallback(async (step: WorkflowStep) => {
    if (!guidedTeachingSession || guidedTeachingBusy) return;
    setGuidedTeachingBusy(true);
    try {
      await callTeachingStepEndpoint(step.id, "POST", "/redo");
      setGuidedTeachingMessages((current) => [...current, { role: "assistant", message: "Okay, let's redo that step." }]);
    } catch (error) {
      setGuidedTeachingMessages((current) => [
        ...current,
        {
          role: "assistant",
          message: `I couldn't redo that step: ${error instanceof Error ? error.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setGuidedTeachingBusy(false);
    }
  }, [callTeachingStepEndpoint, guidedTeachingBusy, guidedTeachingSession]);

  const handleAddDetail = useCallback((step: WorkflowStep) => {
    setGuidedTeachingTargetStepId(step.id);
    setGuidedTeachingInput(`Additional detail for Step ${step.order}: `);
    setGuidedTeachingMessages((current) => [
      ...current,
      { role: "assistant", message: "Got it. Add the detail and I'll attach it to this step." },
    ]);
  }, []);

  const confirmGuidedTeachingStep = useCallback(async (stepId: string) => {
    if (!guidedTeachingSession || guidedTeachingBusy) return;
    setGuidedTeachingBusy(true);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }
      const response = await fetch(`${apiBase}/api/teaching/session/${guidedTeachingSession.sessionId}/steps/${stepId}/confirm`, {
        method: "POST",
      });
      const body = (await response.json()) as TeachingSessionApiResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail ?? `Confirm step failed (${response.status})`);
      }
      applyGuidedTeachingApiResponse(body);
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
  }, [applyGuidedTeachingApiResponse, guidedTeachingBusy, guidedTeachingSession]);

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

  const submitGuidedTeachingMessage = useCallback(async (overrideMessage?: string) => {
    if (!guidedTeachingSession || guidedTeachingBusy) return;
    const message = (overrideMessage ?? guidedTeachingInput).trim();
    if (!message) return;

    const normalized = message.toLowerCase().replace(/\s+/g, " ").trim();
    const latestStep = getLatestRelevantStep();

    setGuidedTeachingMessages((current) => [...current, { role: "user", message }]);
    setGuidedTeachingInput("");

    if (latestStep) {
      if (/(^|\b)(delete the last step|remove the last step)(\b|$)/.test(normalized)) {
        await handleDeleteStep(latestStep, "No problem, I removed that step.");
        return;
      }

      if (/(^|\b)(that click wasn't important|that click was not important|not important)(\b|$)/.test(normalized)) {
        await handleNotImportant(latestStep);
        return;
      }

      if (/(^|\b)(redo that step|redo last step)(\b|$)/.test(normalized)) {
        await handleRedoStep(latestStep);
        return;
      }

      if (/(^|\b)(no that's wrong|no thats wrong|that's wrong|that is wrong)(\b|$)/.test(normalized)) {
        handleEditStep(latestStep);
        setGuidedTeachingMessages((current) => [...current, { role: "assistant", message: "I opened that step for editing." }]);
        return;
      }

      if (/(^|\b)(add detail|add more detail|additional detail)(\b|$)/.test(normalized)) {
        handleAddDetail(latestStep);
        return;
      }
    }

    const targetStepId = guidedTeachingTargetStepId;
    setGuidedTeachingBusy(true);
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
      setGuidedTeachingFromSession(mapped);
      setGuidedTeachingCopilotNotice(body.copilot_notice ?? null);
      setGuidedTeachingCopilotInterpretation(body.copilot_interpretation ?? null);
      setGuidedTeachingCopilotQuestion(body.copilot_question ?? null);
      setGuidedTeachingApprovalMessage(null);
      setGuidedTeachingTargetStepId(null);
      setGuidedTeachingMessages((current) => [...current, { role: "assistant", message: body.reply }]);
    } catch (error) {
      setGuidedTeachingMessages((current) => [
        ...current,
        {
          role: "assistant",
          message: `I couldn't process that teaching update: ${error instanceof Error ? error.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setGuidedTeachingBusy(false);
    }
  }, [
    getLatestRelevantStep,
    guidedTeachingSession,
    guidedTeachingBusy,
    guidedTeachingInput,
    handleDeleteStep,
    handleNotImportant,
    handleRedoStep,
    handleEditStep,
    handleAddDetail,
    guidedTeachingTargetStepId,
    mapApiTeachingSession,
    setGuidedTeachingFromSession,
  ]);

  const confirmCurrentPageAsStartingPage = useCallback(async () => {
    if (!guidedTeachingSession || guidedTeachingBusy) return;
    const candidateUrl = observedCurrentPage || suggestedStartUrl;
    if (!candidateUrl) {
      setGuidedTeachingMessages((current) => [
        ...current,
        { role: "assistant", message: "I can't confirm a starting page yet because no page URL is visible." },
      ]);
      return;
    }
    setGuidedTeachingBusy(true);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }
      const response = await fetch(`${apiBase}/api/teaching/session/${guidedTeachingSession.sessionId}/confirm-start-page`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: candidateUrl }),
      });
      const body = (await response.json()) as TeachingSessionApiResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail ?? `Confirm starting page failed (${response.status})`);
      }
      applyGuidedTeachingApiResponse(body);
      setGuidedTeachingMessages((current) => [...current, { role: "assistant", message: body.reply }]);
    } catch (error) {
      setGuidedTeachingMessages((current) => [
        ...current,
        {
          role: "assistant",
          message: `I couldn't save the starting page yet: ${error instanceof Error ? error.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setGuidedTeachingBusy(false);
    }
  }, [applyGuidedTeachingApiResponse, guidedTeachingBusy, guidedTeachingSession, observedCurrentPage, suggestedStartUrl]);

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
      setGuidedTeachingExecutionReadiness(null);
      setGuidedTeachingWarnings([]);
      setGuidedTeachingApprovalMessage(null);
      setGuidedTeachingRunNowMessage(null);
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

  const runGuidedTeachingWorkflowNow = async () => {
    if (!guidedTeachingSession || guidedTeachingRunNowBusy) {
      return;
    }

    const readiness = guidedTeachingEffectiveReadiness;
    if (!readiness?.runnable) {
      const firstReason = (readiness?.blocking_reasons ?? [])[0] ?? "This workflow needs more teaching before it can run.";
      setGuidedTeachingRunNowMessage(`Can't run yet: ${firstReason}`);
      return;
    }

    setGuidedTeachingRunNowBusy(true);
    setGuidedTeachingRunNowMessage(null);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const slug = workflowSlug(guidedTeachingSession.workflowName);
      const requestBody: Record<string, unknown> = {
        mode: "interactive_visible",
        payload: {},
      };
      const preferredWorker =
        teachingStartupState?.target_machine_uuid || teachingTargetWorkerUuid || targetMachineUuid;
      if (preferredWorker) {
        requestBody.target_machine_uuid = preferredWorker;
      }

      const response = await fetch(`${apiBase}/api/workflows/${slug}/run-taught`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      const body = (await response.json()) as TaskCreateResponse & {
        detail?: string | { message?: string };
        blocking_reasons?: string[];
      };

      if (!response.ok) {
        const reason = (body.blocking_reasons ?? [])[0]
          ?? (typeof body.detail === "string" ? body.detail : body.detail?.message)
          ?? `Workflow run failed (${response.status})`;
        setGuidedTeachingRunNowMessage(`Couldn't start run: ${reason}`);
        return;
      }

      setResponse(body);
      setTaskActionFeedback({
        kind: "success",
        message: `Started '${guidedTeachingSession.workflowName}'`,
        timestamp: new Date().toLocaleTimeString(),
      });
      setGuidedTeachingRunNowMessage("Run started. Bill is executing this taught workflow now.");
      await loadDashboardData();
    } catch (error) {
      setGuidedTeachingRunNowMessage(
        `Couldn't start run: ${error instanceof Error ? error.message : "Unknown error"}`,
      );
    } finally {
      setGuidedTeachingRunNowBusy(false);
    }
  };

  const generateGuidedTeachingSop = useCallback(async () => {
    if (guidedTeachingSopBusy) {
      return;
    }

    const draftId = (teachingSessionDraftId || "").trim();
    const workflowName = (guidedTeachingSession?.workflowName || "").trim();
    if (!draftId && !workflowName) {
      setGuidedTeachingSopError("No draft or workflow id is available yet. Approve the draft first.");
      return;
    }

    setGuidedTeachingSopBusy(true);
    setGuidedTeachingSopError(null);
    try {
      const apiBase = getApiBase();
      if (!apiBase) {
        throw new Error("NEXT_PUBLIC_API_BASE is not set");
      }

      const endpoint = draftId
        ? `${apiBase}/api/teaching/drafts/${encodeURIComponent(draftId)}/generate-sop`
        : `${apiBase}/api/workflows/${encodeURIComponent(workflowSlug(workflowName))}/sop`;
      const method = draftId ? "POST" : "GET";

      const response = await fetch(endpoint, {
        method,
        headers: method === "POST" ? { "Content-Type": "application/json" } : undefined,
      });
      const body = (await response.json()) as GeneratedWorkflowSOP & { detail?: string | { message?: string } };
      if (!response.ok) {
        const detail = typeof body.detail === "string" ? body.detail : body.detail?.message;
        throw new Error(detail || `SOP generation failed (${response.status})`);
      }

      setGuidedTeachingSopRecord(body);
      setGuidedTeachingSopError(null);
    } catch (error) {
      setGuidedTeachingSopError(error instanceof Error ? error.message : "Unknown SOP generation error");
    } finally {
      setGuidedTeachingSopBusy(false);
    }
  }, [guidedTeachingSession?.workflowName, guidedTeachingSopBusy, teachingSessionDraftId]);

  const copyGuidedTeachingSop = useCallback(async () => {
    if (!guidedTeachingSopRecord?.markdown) {
      return;
    }
    try {
      await navigator.clipboard.writeText(guidedTeachingSopRecord.markdown);
      setGuidedTeachingSopError(null);
    } catch {
      setGuidedTeachingSopError("Copy failed. Your browser may block clipboard access.");
    }
  }, [guidedTeachingSopRecord]);

  const downloadGuidedTeachingSop = useCallback(() => {
    if (!guidedTeachingSopRecord?.markdown) {
      return;
    }
    const blob = new Blob([guidedTeachingSopRecord.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${workflowSlug(guidedTeachingSopRecord.workflow_name || "workflow")}-sop.md`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }, [guidedTeachingSopRecord]);

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

  const setLoggedOutState = useCallback((message?: string) => {
    setCurrentUser(null);
    setSessionExpiresAt(null);
    setAuthChecking(false);
    setAuthNotice(message ?? "Please log in to continue.");
  }, []);

  const readErrorDetail = async (response: Response): Promise<string> => {
    try {
      const payload = (await response.clone().json()) as { detail?: string; error?: string; message?: string };
      return payload.detail ?? payload.error ?? payload.message ?? `HTTP ${response.status}`;
    } catch {
      return `HTTP ${response.status}`;
    }
  };

  const apiFetch = useCallback(
    async (
      url: string,
      init?: RequestInit & { allowUnauthorized?: boolean },
    ): Promise<Response> => {
      const { allowUnauthorized = false, ...requestInit } = init ?? {};
      const response = await fetch(url, {
        cache: "no-store",
        credentials: "include",
        ...requestInit,
      });
      if (response.status === 401 && !allowUnauthorized) {
        setLoggedOutState("Session expired. Please log in again.");
      }
      return response;
    },
    [setLoggedOutState],
  );

  const fetchJson = useCallback(async <T,>(
    url: string,
    init?: RequestInit & { allowUnauthorized?: boolean },
  ): Promise<T> => {
    console.log(`[auth-proxy] fetching ${url}`);
    const response = await apiFetch(url, init);
    console.log(`[auth-proxy] response ${response.status} for ${url}`);

    if (!response.ok) {
      throw new Error(await readErrorDetail(response));
    }

    return (await response.json()) as T;
  }, [apiFetch]);

  const resolveDownloadUrl = useCallback((downloadUrl: string): URL => {
    const raw = String(downloadUrl || "").trim();
    if (!raw) {
      throw new Error("Download URL is empty.");
    }

    const looksAbsolute = /^https?:\/\//i.test(raw);
    const resolved = looksAbsolute ? new URL(raw) : new URL(raw, getWorkerApiBase());

    // Avoid mixed-content blocking when frontend is HTTPS, but only upgrade
    // direct worker downloads targeting the configured Beanstalk backend host.
    if (typeof window !== "undefined" && window.location.protocol === "https:" && resolved.protocol === "http:") {
      try {
        const workerBaseHost = new URL(getWorkerApiBase()).hostname;
        const sameWorkerHost = resolved.hostname === workerBaseHost;
        const isBeanstalkHost = /(?:^|\.)elasticbeanstalk\.com$/i.test(resolved.hostname);
        if (sameWorkerHost && isBeanstalkHost) {
          resolved.protocol = "https:";
        }
      } catch {
        // Ignore base parsing issues and keep the original resolved URL.
      }
    }

    return resolved;
  }, []);

  const triggerBrowserDownload = useCallback((downloadUrl: string): string => {
    const resolved = resolveDownloadUrl(downloadUrl);
    const anchor = document.createElement("a");
    anchor.href = resolved.toString();
    anchor.download = "";
    anchor.target = "_self";
    anchor.rel = "noopener noreferrer";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    return resolved.toString();
  }, [resolveDownloadUrl]);

  const loadCurrentUser = useCallback(async () => {
    const apiBase = getApiBase();
    if (!apiBase) {
      setAuthError("NEXT_PUBLIC_API_BASE is not set. Login is unavailable.");
      setAuthChecking(false);
      return;
    }

    try {
      const response = await apiFetch(`${apiBase}/api/auth/me`, { allowUnauthorized: true });
      if (response.status === 401) {
        setCurrentUser(null);
        setSessionExpiresAt(null);
        setAuthNotice("Please log in to continue.");
        return;
      }
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      const payload = (await response.json()) as BillCurrentUserResponse;
      setCurrentUser(payload.user);
      setAuthError(null);
      setAuthNotice(null);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Unable to validate login session");
    } finally {
      setAuthChecking(false);
    }
  }, [apiFetch]);

  const loadAdminPanels = useCallback(async () => {
    if (currentUser?.role !== "admin") {
      setAdminUsers([]);
      setAdminAuditLogs([]);
      setAdminError(null);
      return;
    }
    const apiBase = getApiBase();
    if (!apiBase) {
      return;
    }

    setAdminBusy(true);
    setAdminError(null);
    try {
      const [users, audits] = await Promise.all([
        fetchJson<BillUserRecord[]>(`${apiBase}/api/admin/users?limit=100`),
        fetchJson<BillAuditLogRecord[]>(`${apiBase}/api/admin/audit-logs?limit=50`),
      ]);
      setAdminUsers(Array.isArray(users) ? users : []);
      setAdminAuditLogs(Array.isArray(audits) ? audits : []);
    } catch (error) {
      setAdminError(error instanceof Error ? error.message : "Admin panel failed to load");
    } finally {
      setAdminBusy(false);
    }
  }, [currentUser?.role]);

  const loadKnowledgePanels = useCallback(async () => {
    const currentRole = currentUser?.role;
    if (!currentRole || currentRole === "viewer") {
      setKnowledgeEntries([]);
      setKnowledgeError(null);
      return;
    }
    const apiBase = getApiBase();
    if (!apiBase) {
      return;
    }

    setKnowledgeLoading(true);
    setKnowledgeError(null);
    try {
      const endpoint =
        currentRole === "admin"
          ? `${apiBase}/api/knowledge?limit=300`
          : `${apiBase}/api/knowledge/active?limit=300`;
      const records = await fetchJson<KnowledgeRecord[]>(endpoint);
      setKnowledgeEntries(Array.isArray(records) ? records : []);
    } catch (error) {
      setKnowledgeError(error instanceof Error ? error.message : "Knowledge Center failed to load");
    } finally {
      setKnowledgeLoading(false);
    }
  }, [currentUser?.role, fetchJson]);

  const submitLogin = useCallback(async () => {
    const apiBase = getApiBase();
    if (!apiBase) {
      setAuthError("NEXT_PUBLIC_API_BASE is not set. Login is unavailable.");
      return;
    }
    if (!loginEmail.trim() || !loginPassword.trim()) {
      setAuthError("Email and password are required.");
      return;
    }

    setLoginBusy(true);
    setAuthError(null);
    try {
      const response = await apiFetch(`${apiBase}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: loginEmail.trim(),
          password: loginPassword,
        }),
        allowUnauthorized: true,
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      const payload = (await response.json()) as BillLoginResponse;
      setCurrentUser(payload.user);
      setSessionExpiresAt(payload.session_expires_at);
      setAuthNotice(null);
      setLoginPassword("");
      setAuthChecking(false);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Login failed");
    } finally {
      setLoginBusy(false);
    }
  }, [apiFetch, loginEmail, loginPassword]);

  const submitLogout = useCallback(async () => {
    const apiBase = getApiBase();
    if (apiBase) {
      try {
        await apiFetch(`${apiBase}/api/auth/logout`, {
          method: "POST",
          allowUnauthorized: true,
        });
      } catch {
        // no-op: client state is authoritative for UI logout
      }
    }
    setLoggedOutState("Logged out.");
  }, [apiFetch, setLoggedOutState]);

  const loadDashboardData = async () => {
    setErrors({});

    const apiBase = getApiBase();
    console.log(`[dashboard] loadDashboardData: apiBase = ${apiBase}, window.location.protocol = ${typeof window !== "undefined" ? window.location.protocol : "N/A"}`);

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
    void loadCurrentUser();
  }, [loadCurrentUser]);

  useEffect(() => {
    if (!currentUser) {
      return;
    }
    void loadDashboardData();
    const interval = setInterval(() => {
      void loadDashboardData();
    }, 3000);

    return () => clearInterval(interval);
  }, [currentUser]);

  useEffect(() => {
    if (!currentUser) {
      return;
    }
    void loadBrainPanels();
    const interval = setInterval(() => {
      void loadBrainPanels();
    }, 7000);

    return () => clearInterval(interval);
  }, [currentUser]);

  useEffect(() => {
    if (currentUser?.role !== "admin") {
      setAdminUsers([]);
      setAdminAuditLogs([]);
      setAdminError(null);
      return;
    }
    void loadAdminPanels();
  }, [currentUser?.role, loadAdminPanels]);

  useEffect(() => {
    if (!currentUser || currentUser.role === "viewer") {
      setKnowledgeEntries([]);
      setKnowledgeError(null);
      return;
    }
    void loadKnowledgePanels();
  }, [currentUser?.role, loadKnowledgePanels]);

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
      const res = await apiFetch(taskCreateUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody)
      });
      console.log(`[dashboard] Response status for ${taskCreateUrl}: ${res.status}`);
      const data = (await res.json()) as TaskCreateResponse;
      setResponse(data);
      if (!res.ok) {
        setActionError(await readErrorDetail(res));
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
      const slug = workflowSlug(workflowName);
      const requestBody: Record<string, unknown> = { mode: "interactive_visible", payload: {} };
      if (slug === "smart_sherpa_sync") {
        requestBody.payload = {
          run_mode: "batch",
          source_record: { run_mode: "batch" },
          target_contact: { run_mode: "batch" },
        };
      }
      if (targetMachineUuid) requestBody.target_machine_uuid = targetMachineUuid;
      const matchingDraft = workflowDrafts.find((d) => {
        const draftNames = [d.workflow_name, d.published_workflow_name ?? ""];
        return draftNames.some((name) => workflowSlug(String(name || "")) === slug);
      });
      const workflowRecord = workflows.find((w) => workflowSlug(w.workflow_name) === slug);
      const isStaticProcedure = STATIC_PROCEDURE_WORKFLOWS.has(slug) || Boolean(workflowRecord?.published_static_procedure);
      const shouldUseRunTaught = !isStaticProcedure && Boolean(matchingDraft);

      if (shouldUseRunTaught) {
        const readiness = matchingDraft?.execution_readiness;
        const runnable = Boolean(readiness?.runnable);
        if (!runnable) {
          const reasons = (readiness?.blocking_reasons ?? []).filter(Boolean);
          const firstReason = reasons[0] ?? "This learned workflow needs more teaching before it can run.";
          setActionError(`Workflow saved, but it is not runnable yet. Reason: ${firstReason}`);
          return;
        }
      }

      const runUrl = shouldUseRunTaught
        ? `${apiBase}/api/workflows/${slug}/run-taught`
        : `${apiBase}/api/procedures/${slug}/run`;

      const finalRes = await fetch(runUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });

      const rawData = await finalRes.json();
      const data = rawData as TaskCreateResponse;
      setResponse(data);
      if (!finalRes.ok) {
        const detail = typeof rawData?.detail === "string"
          ? rawData.detail
          : String(rawData?.detail?.message ?? JSON.stringify(rawData));
        setActionError(`Run '${workflowName}' failed: ${finalRes.status} ${detail}`);
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

  const selectedWorkflowDraft = workflowDrafts.find((d) => {
    const names = [d.workflow_name, d.published_workflow_name ?? ""];
    return names.some((name) => workflowSlug(String(name || "")) === workflowSlug(helperWorkflow));
  });
  const selectedWorkflowRecord = workflows.find((w) => workflowSlug(w.workflow_name) === workflowSlug(helperWorkflow));
  const selectedIsStaticProcedure = STATIC_PROCEDURE_WORKFLOWS.has(workflowSlug(helperWorkflow)) || Boolean(selectedWorkflowRecord?.published_static_procedure);
  const selectedWorkflowRunnable = selectedIsStaticProcedure
    ? true
    : (selectedWorkflowDraft ? Boolean(selectedWorkflowDraft.execution_readiness?.runnable) : true);
  const selectedWorkflowBlockingReason = !selectedWorkflowRunnable
    ? (selectedWorkflowDraft?.execution_readiness?.blocking_reasons?.[0] ?? "This workflow needs more teaching before it can run.")
    : null;

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
          setGuidedTeachingExecutionReadiness(null);
          setGuidedTeachingWarnings([]);
          setGuidedTeachingApprovalMessage(null);
          setGuidedTeachingRunNowMessage(null);
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

  const startTeachingFromCommandCenter = useCallback(() => {
    if (!targetMachineUuid) {
      setChatHistory((current) => [
        ...current,
        {
          role: "assistant",
          message: "Select an online idle worker before starting Teaching Mode.",
        },
      ]);
      return;
    }

    if (!selectedMachine) {
      setChatHistory((current) => [
        ...current,
        {
          role: "assistant",
          message: "The selected worker is unavailable. Pick a worker again before starting Teaching Mode.",
        },
      ]);
      return;
    }

    const selectedStatus = String(selectedMachine.status || "unknown").toLowerCase();
    if (!selectedMachine.online) {
      setChatHistory((current) => [
        ...current,
        {
          role: "assistant",
          message: `${selectedMachine.machine_name} is offline. Start that worker, then retry.`,
        },
      ]);
      return;
    }
    if (!(selectedStatus === "idle" || selectedStatus === "ready")) {
      setChatHistory((current) => [
        ...current,
        {
          role: "assistant",
          message: `${selectedMachine.machine_name} is not idle (status=${selectedMachine.status}). Choose an idle worker and retry.`,
        },
      ]);
      return;
    }

    const suggested = [learningWorkflowName, helperWorkflow, guidedTeachingSession?.workflowName]
      .map((value) => String(value || "").trim())
      .find(Boolean) || "";
    const workflowName = window.prompt("What should this workflow be called?", suggested)?.trim();
    if (!workflowName) {
      return;
    }

    const command = `Let's create a new workflow called ${workflowName}. Teach Bill this workflow step by step.`;
    setChatInput(command);
    setGuidedTeachingRunNowMessage(null);
    void submitBrainCommand(command);
  }, [guidedTeachingSession?.workflowName, helperWorkflow, learningWorkflowName, selectedMachine, targetMachineUuid]);

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

    const formatApiErrorDetail = (detail: unknown): string => {
      if (typeof detail === "string") {
        return detail;
      }
      if (Array.isArray(detail)) {
        return detail.map((item) => formatApiErrorDetail(item)).filter(Boolean).join("; ");
      }
      if (detail && typeof detail === "object") {
        const record = detail as Record<string, unknown>;
        const generalMessage = typeof record.message === "string" ? record.message : "";
        const message = typeof record.msg === "string" ? record.msg : "";
        const location = Array.isArray(record.loc)
          ? record.loc.map((part) => String(part)).join(".")
          : typeof record.loc === "string"
            ? record.loc
            : "";
        const blockingReasons = Array.isArray(record.blocking_reasons)
          ? record.blocking_reasons.map((item) => String(item)).filter(Boolean)
          : [];
        const warnings = Array.isArray(record.warnings)
          ? record.warnings.map((item) => String(item)).filter(Boolean)
          : [];
        if (generalMessage || blockingReasons.length || warnings.length) {
          const parts: string[] = [];
          if (generalMessage) parts.push(generalMessage);
          if (blockingReasons.length) parts.push(`Blocking: ${blockingReasons.join("; ")}`);
          if (warnings.length) parts.push(`Warnings: ${warnings.join("; ")}`);
          return parts.join(" | ");
        }
        if (message) {
          return location ? `${location}: ${message}` : message;
        }
        try {
          return JSON.stringify(detail);
        } catch {
          return String(detail);
        }
      }
      return detail == null ? "" : String(detail);
    };

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
        body: JSON.stringify({
          approved_by: currentUser?.name || currentUser?.email || "bill-web-operator",
        }),
      });
      const body = (await response.json()) as WorkflowLearningDraft | { detail?: unknown };
      if (!response.ok) {
        const detail = formatApiErrorDetail((body as { detail?: unknown }).detail);
        throw new Error(detail || `Publish failed (${response.status})`);
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
      setTeachingOverlayTaskId(data.task_id ?? null);
      setTeachingLaunchStatus("running");
      setFeedback(setLearningFeedback, "success", `Teach browser launch requested. Task ${data.task_id ?? "queued"}.`);
      await loadBrainPanels();
    } catch (err) {
      setTeachingLaunchStatus("error");
      setFeedback(setLearningFeedback, "error", err instanceof Error ? err.message : "Launch failed");
    }
  };

  useEffect(() => {
    const promptId = teachingOverlayQuestion?.question?.prompt_id;
    if (!teachingOverlayOpen || !promptId || !teachingOverlayAutoSpeakQuestions) {
      return;
    }
    if (teachingOverlayQuestion?.settings?.voice_provider === "none") {
      return;
    }
    const minSeconds = Number(teachingOverlayQuestion?.settings?.min_seconds_between_questions ?? 6);

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

  // ── Worker Download Center callbacks ──────────────────────────────────────

  const loadCurrentWorkerRelease = useCallback(async () => {
    const apiBase = getApiBase();
    if (!apiBase || !currentUser) return;
    const allowed = ["admin", "teacher", "runner"] as const;
    if (!allowed.includes(currentUser.role as (typeof allowed)[number])) return;
    setWorkerReleaseLoading(true);
    setWorkerReleaseError(null);
    try {
      const r = await apiFetch(`${apiBase}/api/worker-releases/current`);
      if (r.status === 404) {
        setCurrentWorkerRelease(null);
        return;
      }
      if (!r.ok) throw new Error(await readErrorDetail(r));
      setCurrentWorkerRelease((await r.json()) as WorkerReleasePublicRecord);
    } catch (err) {
      setWorkerReleaseError(err instanceof Error ? err.message : "Failed to load worker release");
    } finally {
      setWorkerReleaseLoading(false);
    }
  }, [apiFetch, currentUser]);

  const downloadCurrentWorker = useCallback(async (releaseId: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setWorkerDownloadBusy(true);
    setWorkerDownloadMessage(null);
    try {
      const r = await apiFetch(`${apiBase}/api/worker-releases/${releaseId}/download-url`, {
        method: "POST",
      });
      if (!r.ok) {
        const msg = await readErrorDetail(r);
        setWorkerDownloadMessage(`Download failed: ${msg}`);
        return;
      }
      const payload = (await r.json()) as WorkerDownloadUrlResponse;
      if (!payload.download_url) {
        setWorkerDownloadMessage("Download failed: backend did not return a download URL.");
        return;
      }
      const openedUrl = triggerBrowserDownload(payload.download_url);
      const openedDomain = new URL(openedUrl).origin;
      setWorkerDownloadMessage(`Download link opened from ${openedDomain}.`);
      void loadCurrentWorkerRelease();
    } catch (err) {
      setWorkerDownloadMessage(err instanceof Error ? err.message : "Download failed");
    } finally {
      setWorkerDownloadBusy(false);
    }
  }, [apiFetch, loadCurrentWorkerRelease, triggerBrowserDownload]);

  const loadAdminWorkerReleases = useCallback(async () => {
    const apiBase = getApiBase();
    if (!apiBase || currentUser?.role !== "admin") return;
    setAdminWorkerReleasesLoading(true);
    setAdminWorkerReleasesError(null);
    try {
      const r = await apiFetch(`${apiBase}/api/worker-releases`);
      if (!r.ok) throw new Error(await readErrorDetail(r));
      setAdminWorkerReleases((await r.json()) as WorkerReleaseAdminRecord[]);
    } catch (err) {
      setAdminWorkerReleasesError(err instanceof Error ? err.message : "Failed to load releases");
    } finally {
      setAdminWorkerReleasesLoading(false);
    }
  }, [apiFetch, currentUser?.role]);

  const registerWorkerRelease = useCallback(async () => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    if (!newReleaseVersion.trim() || !newReleaseFilename.trim()) {
      setAdminWorkerReleasesError("Version and filename are required.");
      return;
    }
    setAdminWorkerReleasesLoading(true);
    setAdminWorkerReleasesError(null);
    try {
      const r = await apiFetch(`${apiBase}/api/worker-releases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          version: newReleaseVersion.trim(),
          package_filename: newReleaseFilename.trim(),
          release_notes: newReleaseNotes.trim() || null,
          channel: newReleaseChannel || "stable",
        }),
      });
      if (!r.ok) throw new Error(await readErrorDetail(r));
      setNewReleaseVersion("");
      setNewReleaseFilename("");
      setNewReleaseNotes("");
      await loadAdminWorkerReleases();
    } catch (err) {
      setAdminWorkerReleasesError(err instanceof Error ? err.message : "Failed to register release");
    } finally {
      setAdminWorkerReleasesLoading(false);
    }
  }, [apiFetch, newReleaseVersion, newReleaseFilename, newReleaseNotes, newReleaseChannel, loadAdminWorkerReleases]);

  const markReleaseCurrent = useCallback(async (releaseId: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setAdminWorkerReleasesLoading(true);
    try {
      const r = await apiFetch(`${apiBase}/api/worker-releases/${releaseId}/mark-current`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      if (!r.ok) throw new Error(await readErrorDetail(r));
      await loadAdminWorkerReleases();
      await loadCurrentWorkerRelease();
    } catch (err) {
      setAdminWorkerReleasesError(err instanceof Error ? err.message : "Failed to mark release current");
    } finally {
      setAdminWorkerReleasesLoading(false);
    }
  }, [apiFetch, loadAdminWorkerReleases, loadCurrentWorkerRelease]);

  const disableRelease = useCallback(async (releaseId: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setAdminWorkerReleasesLoading(true);
    try {
      const r = await apiFetch(`${apiBase}/api/worker-releases/${releaseId}/disable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      if (!r.ok) throw new Error(await readErrorDetail(r));
      await loadAdminWorkerReleases();
    } catch (err) {
      setAdminWorkerReleasesError(err instanceof Error ? err.message : "Failed to disable release");
    } finally {
      setAdminWorkerReleasesLoading(false);
    }
  }, [apiFetch, loadAdminWorkerReleases]);

  // Load worker release when a user with download permission logs in.
  useEffect(() => {
    if (!currentUser) {
      setCurrentWorkerRelease(null);
      setAdminWorkerReleases([]);
      return;
    }
    const downloadRoles = ["admin", "teacher", "runner"];
    if (downloadRoles.includes(currentUser.role)) {
      void loadCurrentWorkerRelease();
    }
    if (currentUser.role === "admin") {
      void loadAdminWorkerReleases();
    }
  }, [currentUser?.role, loadCurrentWorkerRelease, loadAdminWorkerReleases]);

  // ── Extension Download Center callbacks ───────────────────────────────────

  const loadCurrentExtensionRelease = useCallback(async () => {
    const apiBase = getApiBase();
    if (!apiBase || !currentUser) return;
    const allowed = ["admin", "teacher", "runner"] as const;
    if (!allowed.includes(currentUser.role as (typeof allowed)[number])) return;
    setExtensionReleaseLoading(true);
    setExtensionReleaseError(null);
    try {
      const r = await apiFetch(`${apiBase}/api/extension-releases/current`);
      if (r.status === 404) {
        setCurrentExtensionRelease(null);
        return;
      }
      if (!r.ok) throw new Error(await readErrorDetail(r));
      setCurrentExtensionRelease((await r.json()) as ExtensionReleasePublicRecord);
    } catch (err) {
      setExtensionReleaseError(err instanceof Error ? err.message : "Failed to load extension release");
    } finally {
      setExtensionReleaseLoading(false);
    }
  }, [apiFetch, currentUser]);

  const downloadCurrentExtension = useCallback(async (releaseId: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setExtensionDownloadBusy(true);
    setExtensionDownloadMessage(null);
    try {
      const r = await apiFetch(`${apiBase}/api/extension-releases/${releaseId}/download-url`, {
        method: "POST",
      });
      if (!r.ok) {
        const msg = await readErrorDetail(r);
        setExtensionDownloadMessage(`Download failed: ${msg}`);
        return;
      }
      const payload = (await r.json()) as ExtensionDownloadUrlResponse;
      if (!payload.download_url) {
        setExtensionDownloadMessage("Download failed: backend did not return a download URL.");
        return;
      }
      const openedUrl = triggerBrowserDownload(payload.download_url);
      const openedDomain = new URL(openedUrl).origin;
      setExtensionDownloadMessage(`Download link opened from ${openedDomain}.`);
      void loadCurrentExtensionRelease();
    } catch (err) {
      setExtensionDownloadMessage(err instanceof Error ? err.message : "Download failed");
    } finally {
      setExtensionDownloadBusy(false);
    }
  }, [apiFetch, loadCurrentExtensionRelease, triggerBrowserDownload]);

  const loadAdminExtensionReleases = useCallback(async () => {
    const apiBase = getApiBase();
    if (!apiBase || currentUser?.role !== "admin") return;
    setAdminExtensionReleasesLoading(true);
    setAdminExtensionReleasesError(null);
    try {
      const r = await apiFetch(`${apiBase}/api/extension-releases`);
      if (!r.ok) throw new Error(await readErrorDetail(r));
      setAdminExtensionReleases((await r.json()) as ExtensionReleaseAdminRecord[]);
    } catch (err) {
      setAdminExtensionReleasesError(err instanceof Error ? err.message : "Failed to load extension releases");
    } finally {
      setAdminExtensionReleasesLoading(false);
    }
  }, [apiFetch, currentUser?.role]);

  const registerExtensionRelease = useCallback(async () => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    if (!newExtensionVersionLabel.trim() || !newExtensionFilename.trim()) {
      setAdminExtensionReleasesError("Version label and filename are required.");
      return;
    }
    setAdminExtensionReleasesLoading(true);
    setAdminExtensionReleasesError(null);
    try {
      const r = await apiFetch(`${apiBase}/api/extension-releases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          version_label: newExtensionVersionLabel.trim(),
          file_name: newExtensionFilename.trim(),
          release_notes: newExtensionReleaseNotes.trim() || null,
        }),
      });
      if (!r.ok) throw new Error(await readErrorDetail(r));
      setNewExtensionVersionLabel("");
      setNewExtensionFilename("");
      setNewExtensionReleaseNotes("");
      await loadAdminExtensionReleases();
      await loadCurrentExtensionRelease();
    } catch (err) {
      setAdminExtensionReleasesError(err instanceof Error ? err.message : "Failed to register extension release");
    } finally {
      setAdminExtensionReleasesLoading(false);
    }
  }, [
    apiFetch,
    newExtensionVersionLabel,
    newExtensionFilename,
    newExtensionReleaseNotes,
    loadAdminExtensionReleases,
    loadCurrentExtensionRelease,
  ]);

  const markExtensionReleaseCurrent = useCallback(async (releaseId: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setAdminExtensionReleasesLoading(true);
    try {
      const r = await apiFetch(`${apiBase}/api/extension-releases/${releaseId}/mark-current`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      if (!r.ok) throw new Error(await readErrorDetail(r));
      await loadAdminExtensionReleases();
      await loadCurrentExtensionRelease();
    } catch (err) {
      setAdminExtensionReleasesError(err instanceof Error ? err.message : "Failed to mark extension release current");
    } finally {
      setAdminExtensionReleasesLoading(false);
    }
  }, [apiFetch, loadAdminExtensionReleases, loadCurrentExtensionRelease]);

  const disableExtensionRelease = useCallback(async (releaseId: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setAdminExtensionReleasesLoading(true);
    try {
      const r = await apiFetch(`${apiBase}/api/extension-releases/${releaseId}/disable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      if (!r.ok) throw new Error(await readErrorDetail(r));
      await loadAdminExtensionReleases();
    } catch (err) {
      setAdminExtensionReleasesError(err instanceof Error ? err.message : "Failed to disable extension release");
    } finally {
      setAdminExtensionReleasesLoading(false);
    }
  }, [apiFetch, loadAdminExtensionReleases]);

  useEffect(() => {
    if (!currentUser) {
      setCurrentExtensionRelease(null);
      setAdminExtensionReleases([]);
      return;
    }
    const downloadRoles = ["admin", "teacher", "runner"];
    if (downloadRoles.includes(currentUser.role)) {
      void loadCurrentExtensionRelease();
    }
    if (currentUser.role === "admin") {
      void loadAdminExtensionReleases();
    }
  }, [currentUser?.role, loadCurrentExtensionRelease, loadAdminExtensionReleases]);

  const createAdminUser = useCallback(async () => {
    if (!newUserName.trim() || !newUserEmail.trim() || !newUserPassword.trim()) {
      setAdminError("Name, email, and password are required.");
      return;
    }
    const apiBase = getApiBase();
    if (!apiBase) {
      return;
    }

    setAdminBusy(true);
    setAdminError(null);
    try {
      const response = await apiFetch(`${apiBase}/api/admin/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newUserName.trim(),
          email: newUserEmail.trim().toLowerCase(),
          password: newUserPassword,
          role: newUserRole,
          status: "active",
        }),
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      setNewUserName("");
      setNewUserEmail("");
      setNewUserPassword("");
      setNewUserRole("viewer");
      await loadAdminPanels();
    } catch (error) {
      setAdminError(error instanceof Error ? error.message : "Unable to create user");
    } finally {
      setAdminBusy(false);
    }
  }, [apiFetch, loadAdminPanels, newUserEmail, newUserName, newUserPassword, newUserRole]);

  const updateAdminUser = useCallback(
    async (userId: string, changes: Partial<Pick<BillUserRecord, "role" | "status">>) => {
      const apiBase = getApiBase();
      if (!apiBase) {
        return;
      }
      setAdminBusy(true);
      setAdminError(null);
      try {
        const response = await apiFetch(`${apiBase}/api/admin/users/${userId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(changes),
        });
        if (!response.ok) {
          throw new Error(await readErrorDetail(response));
        }
        await loadAdminPanels();
      } catch (error) {
        setAdminError(error instanceof Error ? error.message : "Unable to update user");
      } finally {
        setAdminBusy(false);
      }
    },
    [apiFetch, loadAdminPanels],
  );

  const createKnowledgeEntry = useCallback(async (payload: {
    title: string;
    category: string;
    applies_to: string[];
    content: string;
    source_type: "manual" | "document" | "imported" | "system";
    tags: string[];
    status: "active" | "draft" | "archived";
    tenant_id?: string | null;
  }) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setKnowledgeActionBusyKey("knowledge-create");
    setKnowledgeActionFeedback(null);
    setKnowledgeError(null);
    try {
      const response = await apiFetch(`${apiBase}/api/knowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      await loadKnowledgePanels();
      setKnowledgeActionFeedback({
        kind: "success",
        message: "Knowledge entry created.",
        timestamp: new Date().toLocaleTimeString(),
      });
    } catch (error) {
      setKnowledgeError(error instanceof Error ? error.message : "Failed to create knowledge entry");
      setKnowledgeActionFeedback({
        kind: "error",
        message: error instanceof Error ? error.message : "Failed to create knowledge entry",
        timestamp: new Date().toLocaleTimeString(),
      });
    } finally {
      setKnowledgeActionBusyKey(null);
    }
  }, [apiFetch, loadKnowledgePanels]);

  const updateKnowledgeEntry = useCallback(async (
    knowledgeId: string,
    payload: {
      title?: string;
      category?: string;
      applies_to?: string[];
      content?: string;
      source_type?: "manual" | "document" | "imported" | "system";
      tags?: string[];
      status?: "active" | "draft" | "archived";
      tenant_id?: string | null;
    }
  ) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setKnowledgeActionBusyKey(`knowledge-update-${knowledgeId}`);
    setKnowledgeActionFeedback(null);
    setKnowledgeError(null);
    try {
      const response = await apiFetch(`${apiBase}/api/knowledge/${knowledgeId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      await loadKnowledgePanels();
      setKnowledgeActionFeedback({
        kind: "success",
        message: "Knowledge entry saved.",
        timestamp: new Date().toLocaleTimeString(),
      });
    } catch (error) {
      setKnowledgeError(error instanceof Error ? error.message : "Failed to update knowledge entry");
      setKnowledgeActionFeedback({
        kind: "error",
        message: error instanceof Error ? error.message : "Failed to update knowledge entry",
        timestamp: new Date().toLocaleTimeString(),
      });
    } finally {
      setKnowledgeActionBusyKey(null);
    }
  }, [apiFetch, loadKnowledgePanels]);

  const archiveKnowledgeEntry = useCallback(async (knowledgeId: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setKnowledgeActionBusyKey(`knowledge-archive-${knowledgeId}`);
    setKnowledgeActionFeedback(null);
    setKnowledgeError(null);
    try {
      const response = await apiFetch(`${apiBase}/api/knowledge/${knowledgeId}/archive`, { method: "POST" });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      await loadKnowledgePanels();
      setKnowledgeActionFeedback({
        kind: "success",
        message: "Knowledge entry archived.",
        timestamp: new Date().toLocaleTimeString(),
      });
    } catch (error) {
      setKnowledgeError(error instanceof Error ? error.message : "Failed to archive knowledge entry");
      setKnowledgeActionFeedback({
        kind: "error",
        message: error instanceof Error ? error.message : "Failed to archive knowledge entry",
        timestamp: new Date().toLocaleTimeString(),
      });
    } finally {
      setKnowledgeActionBusyKey(null);
    }
  }, [apiFetch, loadKnowledgePanels]);

  const activateKnowledgeEntry = useCallback(async (knowledgeId: string) => {
    const apiBase = getApiBase();
    if (!apiBase) return;
    setKnowledgeActionBusyKey(`knowledge-activate-${knowledgeId}`);
    setKnowledgeActionFeedback(null);
    setKnowledgeError(null);
    try {
      const response = await apiFetch(`${apiBase}/api/knowledge/${knowledgeId}/activate`, { method: "POST" });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      await loadKnowledgePanels();
      setKnowledgeActionFeedback({
        kind: "success",
        message: "Knowledge entry activated.",
        timestamp: new Date().toLocaleTimeString(),
      });
    } catch (error) {
      setKnowledgeError(error instanceof Error ? error.message : "Failed to activate knowledge entry");
      setKnowledgeActionFeedback({
        kind: "error",
        message: error instanceof Error ? error.message : "Failed to activate knowledge entry",
        timestamp: new Date().toLocaleTimeString(),
      });
    } finally {
      setKnowledgeActionBusyKey(null);
    }
  }, [apiFetch, loadKnowledgePanels]);

  if (authChecking) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#070a11] px-4 text-slate-100">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/80 px-6 py-5 text-sm text-slate-300">
          Checking login session...
        </div>
      </main>
    );
  }

  if (!currentUser) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#070a11] px-4 text-slate-100">
        <section className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/85 p-6 shadow-xl shadow-cyan-950/30">
          <h1 className="text-xl font-semibold text-slate-50">Bill Login</h1>
          <p className="mt-2 text-sm text-slate-300">Sign in to access dashboard, teaching, and workflow controls.</p>
          {authNotice && (
            <p className="mt-3 rounded-lg border border-amber-400/35 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">{authNotice}</p>
          )}
          {authError && (
            <p className="mt-3 rounded-lg border border-rose-400/35 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">{authError}</p>
          )}
          <div className="mt-4 space-y-3">
            <input
              value={loginEmail}
              onChange={(event) => setLoginEmail(event.target.value)}
              placeholder="Email"
              autoComplete="username"
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400/60"
            />
            <input
              type="password"
              value={loginPassword}
              onChange={(event) => setLoginPassword(event.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void submitLogin();
                }
              }}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400/60"
            />
            <button
              type="button"
              onClick={() => void submitLogin()}
              disabled={loginBusy}
              className="w-full rounded-xl bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loginBusy ? "Signing in..." : "Sign in"}
            </button>
          </div>
        </section>
      </main>
    );
  }

  if (currentUser.role === "super_admin") {
    return (
      <main className="min-h-screen bg-[#070a11] px-4 py-6 text-slate-100 lg:px-6">
        <div className="mx-auto max-w-[1600px]">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm">
            <div className="text-slate-200">
              <span className="font-semibold text-slate-50">{currentUser.name}</span>
              <span className="mx-2 text-slate-500">•</span>
              <span className="uppercase tracking-wide text-amber-200">{currentUser.role}</span>
              <span className="mx-2 text-slate-500">•</span>
              <span className="text-slate-400">{currentUser.email}</span>
              {sessionExpiresAt && (
                <span className="ml-3 text-xs text-slate-500">Session expires: {toDisplayTime(sessionExpiresAt)}</span>
              )}
            </div>
            <button
              type="button"
              onClick={() => void submitLogout()}
              className={BUTTON_SECONDARY}
            >
              Log out
            </button>
          </div>

          <SuperAdminControlPlane
            apiBase={getApiBase()}
            apiFetch={apiFetch}
            currentUser={{
              id: currentUser.id,
              name: currentUser.name,
              email: currentUser.email,
              role: "super_admin",
            }}
          />
        </div>
      </main>
    );
  }

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

          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm">
            <div className="text-slate-200">
              <span className="font-semibold text-slate-50">{currentUser.name}</span>
              <span className="mx-2 text-slate-500">•</span>
              <span className="uppercase tracking-wide text-cyan-200">{currentUser.role}</span>
              <span className="mx-2 text-slate-500">•</span>
              <span className="text-slate-400">{currentUser.email}</span>
              {sessionExpiresAt && (
                <span className="ml-3 text-xs text-slate-500">Session expires: {toDisplayTime(sessionExpiresAt)}</span>
              )}
            </div>
            <button
              type="button"
              onClick={() => void submitLogout()}
              className={BUTTON_SECONDARY}
            >
              Log out
            </button>
          </div>

          {errors.config && (
            <div className="mb-4 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {errors.config}
            </div>
          )}

          {currentUser.role === "admin" && (
            <section className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-base font-semibold text-slate-50">User & Audit Admin</h2>
                <button type="button" onClick={() => void loadAdminPanels()} className={BUTTON_SECONDARY} disabled={adminBusy}>
                  {adminBusy ? "Refreshing..." : "Refresh"}
                </button>
              </div>
              {adminError && (
                <p className="mt-3 rounded-lg border border-rose-400/35 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">{adminError}</p>
              )}
              <div className="mt-4 grid gap-4 xl:grid-cols-2">
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                  <p className="text-xs uppercase tracking-[0.14em] text-slate-400">Create User</p>
                  <div className="mt-2 grid gap-2 md:grid-cols-2">
                    <input value={newUserName} onChange={(event) => setNewUserName(event.target.value)} placeholder="Name" className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
                    <input value={newUserEmail} onChange={(event) => setNewUserEmail(event.target.value)} placeholder="Email" className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
                    <input type="password" value={newUserPassword} onChange={(event) => setNewUserPassword(event.target.value)} placeholder="Password" className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100" />
                    <select value={newUserRole} onChange={(event) => setNewUserRole(event.target.value as BillUserRole)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100">
                      <option value="viewer">viewer</option>
                      <option value="runner">runner</option>
                      <option value="teacher">teacher</option>
                      <option value="admin">admin</option>
                    </select>
                  </div>
                  <button type="button" onClick={() => void createAdminUser()} disabled={adminBusy} className="mt-3 rounded-lg bg-cyan-500 px-3 py-2 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50">
                    Create user
                  </button>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                  <p className="text-xs uppercase tracking-[0.14em] text-slate-400">Recent Audit Events</p>
                  <div className="mt-2 max-h-44 overflow-auto text-xs text-slate-300">
                    {adminAuditLogs.length === 0 ? (
                      <p className="text-slate-500">No audit entries loaded.</p>
                    ) : (
                      <table className="w-full text-left">
                        <thead className="text-slate-500">
                          <tr>
                            <th className="py-1 pr-2">Time</th>
                            <th className="py-1 pr-2">Event</th>
                            <th className="py-1 pr-2">Actor</th>
                            <th className="py-1">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {adminAuditLogs.slice(0, 25).map((entry) => (
                            <tr key={entry.id} className="border-t border-slate-800/70">
                              <td className="py-1 pr-2 text-slate-400">{toDisplayTime(entry.created_at)}</td>
                              <td className="py-1 pr-2">{entry.event_type}</td>
                              <td className="py-1 pr-2">{entry.actor_user_name || "system"}</td>
                              <td className="py-1">{entry.status_code ?? "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>
              </div>

              <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                <p className="mb-2 text-xs uppercase tracking-[0.14em] text-slate-400">Users</p>
                <table className="min-w-full text-left text-xs text-slate-200">
                  <thead className="text-slate-500">
                    <tr>
                      <th className="py-1 pr-2">Name</th>
                      <th className="py-1 pr-2">Email</th>
                      <th className="py-1 pr-2">Role</th>
                      <th className="py-1 pr-2">Status</th>
                      <th className="py-1 pr-2">Last login</th>
                      <th className="py-1">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {adminUsers.map((user) => (
                      <tr key={user.id} className="border-t border-slate-800/70">
                        <td className="py-1 pr-2">{user.name}</td>
                        <td className="py-1 pr-2 text-slate-400">{user.email}</td>
                        <td className="py-1 pr-2">{user.role}</td>
                        <td className="py-1 pr-2">{user.status}</td>
                        <td className="py-1 pr-2 text-slate-400">{toDisplayTime(user.last_login_at ?? undefined)}</td>
                        <td className="py-1">
                          <div className="flex flex-wrap gap-2">
                            <button type="button" disabled={adminBusy} className={BUTTON_ACCENT_GHOST} onClick={() => void updateAdminUser(user.id, { status: user.status === "active" ? "inactive" : "active" })}>
                              {user.status === "active" ? "Deactivate" : "Activate"}
                            </button>
                            <button type="button" disabled={adminBusy || user.role === "admin"} className={BUTTON_SECONDARY} onClick={() => void updateAdminUser(user.id, { role: "admin" })}>
                              Promote to admin
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* ── Worker Download Center ────────────────────────────────────────────── */}
          {currentUser && ["admin", "teacher", "runner"].includes(currentUser.role) && (
            <section id="extension-download-center" className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-base font-semibold text-slate-50">Worker Downloads</h2>
                <button
                  type="button"
                  className={BUTTON_SECONDARY}
                  onClick={() => void loadCurrentWorkerRelease()}
                  disabled={workerReleaseLoading}
                >
                  {workerReleaseLoading ? "Loading..." : "Refresh"}
                </button>
              </div>

              {workerReleaseError && (
                <p className="mt-3 rounded-lg border border-rose-400/35 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">{workerReleaseError}</p>
              )}

              {!currentWorkerRelease && !workerReleaseLoading && !workerReleaseError && (
                <p className="mt-3 text-sm text-slate-400">No current worker release is available. Ask an admin.</p>
              )}

              {currentWorkerRelease && (
                <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950/60 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-base font-semibold text-slate-50">{currentWorkerRelease.version}</span>
                        <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-300">Current Good Build</span>
                      </div>
                      <p className="mt-1 text-xs text-slate-400">{currentWorkerRelease.package_filename}</p>
                    </div>
                    <button
                      type="button"
                      disabled={workerDownloadBusy}
                      onClick={() => void downloadCurrentWorker(currentWorkerRelease.id)}
                      className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {workerDownloadBusy ? "Downloading..." : "Download Worker"}
                    </button>
                  </div>

                  <dl className="mt-3 grid gap-y-1.5 text-xs sm:grid-cols-2">
                    <div>
                      <dt className="text-slate-500">Released</dt>
                      <dd className="text-slate-200">{new Date(currentWorkerRelease.upload_time).toLocaleString()}</dd>
                    </div>
                    {currentWorkerRelease.released_by_name && (
                      <div>
                        <dt className="text-slate-500">Released by</dt>
                        <dd className="text-slate-200">{currentWorkerRelease.released_by_name}</dd>
                      </div>
                    )}
                    {currentWorkerRelease.file_size_bytes != null && (
                      <div>
                        <dt className="text-slate-500">File size</dt>
                        <dd className="text-slate-200">{(currentWorkerRelease.file_size_bytes / 1024 / 1024).toFixed(1)} MB</dd>
                      </div>
                    )}
                    <div>
                      <dt className="text-slate-500">Downloads</dt>
                      <dd className="text-slate-200">{currentWorkerRelease.download_count}</dd>
                    </div>
                    {currentWorkerRelease.package_sha256 && (
                      <div className="sm:col-span-2">
                        <dt className="text-slate-500">SHA-256</dt>
                        <dd className="flex items-center gap-2 break-all font-mono text-[10px] text-slate-300">
                          {currentWorkerRelease.package_sha256}
                          <button
                            type="button"
                            className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700"
                            onClick={() => void navigator.clipboard.writeText(currentWorkerRelease.package_sha256 ?? "")}
                          >
                            Copy
                          </button>
                        </dd>
                      </div>
                    )}
                    {currentWorkerRelease.release_notes && (
                      <div className="sm:col-span-2">
                        <dt className="text-slate-500">Release notes</dt>
                        <dd className="text-slate-200">{currentWorkerRelease.release_notes}</dd>
                      </div>
                    )}
                  </dl>

                  {workerDownloadMessage && (
                    <p className="mt-2 text-xs text-cyan-300">{workerDownloadMessage}</p>
                  )}

                  <details className="mt-4">
                    <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200">Install instructions</summary>
                    <ol className="mt-2 space-y-1 pl-4 text-xs text-slate-300" style={{listStyleType: "decimal"}}>
                      <li>Download the zip using the button above.</li>
                      <li>Extract the entire folder to a stable location (e.g. Desktop or Documents).</li>
                      <li>Open the extracted folder and run <span className="font-mono">BillWorker.exe</span>.</li>
                      <li>Keep the folder in the same location — do not move it after first run.</li>
                      <li>If antivirus flags it, contact Jared or an admin before deleting or quarantining.</li>
                      <li>Only use the release marked <strong>Current Good Build</strong>.</li>
                    </ol>
                  </details>
                </div>
              )}
            </section>
          )}

          {currentUser && currentUser.role === "viewer" && (
            <section className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
              <h2 className="text-base font-semibold text-slate-50">Worker Downloads</h2>
              <p className="mt-2 text-sm text-slate-400">You do not have permission to download the Bill Worker.</p>
            </section>
          )}

          {/* ── Extension Download Center ─────────────────────────────────────────── */}
          {currentUser && ["admin", "teacher", "runner"].includes(currentUser.role) && (
            <section className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-base font-semibold text-slate-50">Extension Downloads</h2>
                <button
                  type="button"
                  className={BUTTON_SECONDARY}
                  onClick={() => void loadCurrentExtensionRelease()}
                  disabled={extensionReleaseLoading}
                >
                  {extensionReleaseLoading ? "Loading..." : "Refresh"}
                </button>
              </div>

              {extensionReleaseError && (
                <p className="mt-3 rounded-lg border border-rose-400/35 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">{extensionReleaseError}</p>
              )}

              {!currentExtensionRelease && !extensionReleaseLoading && !extensionReleaseError && (
                <p className="mt-3 text-sm text-slate-400">No current extension release is available. Ask an admin.</p>
              )}

              {currentExtensionRelease && (
                <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950/60 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-base font-semibold text-slate-50">{currentExtensionRelease.version_label}</span>
                        <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-300">Current Good Build</span>
                      </div>
                      <p className="mt-1 text-xs text-slate-400">{currentExtensionRelease.file_name}</p>
                    </div>
                    <button
                      type="button"
                      disabled={extensionDownloadBusy}
                      onClick={() => void downloadCurrentExtension(currentExtensionRelease.id)}
                      className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {extensionDownloadBusy ? "Downloading..." : "Download Extension"}
                    </button>
                  </div>

                  <dl className="mt-3 grid gap-y-1.5 text-xs sm:grid-cols-2">
                    <div>
                      <dt className="text-slate-500">Released</dt>
                      <dd className="text-slate-200">{new Date(currentExtensionRelease.released_at).toLocaleString()}</dd>
                    </div>
                    {currentExtensionRelease.released_by_name && (
                      <div>
                        <dt className="text-slate-500">Released by</dt>
                        <dd className="text-slate-200">{currentExtensionRelease.released_by_name}</dd>
                      </div>
                    )}
                    {currentExtensionRelease.file_size_bytes != null && (
                      <div>
                        <dt className="text-slate-500">File size</dt>
                        <dd className="text-slate-200">{(currentExtensionRelease.file_size_bytes / 1024 / 1024).toFixed(1)} MB</dd>
                      </div>
                    )}
                    <div>
                      <dt className="text-slate-500">Downloads</dt>
                      <dd className="text-slate-200">{currentExtensionRelease.download_count}</dd>
                    </div>
                    {currentExtensionRelease.sha256_hash && (
                      <div className="sm:col-span-2">
                        <dt className="text-slate-500">SHA-256</dt>
                        <dd className="flex items-center gap-2 break-all font-mono text-[10px] text-slate-300">
                          {currentExtensionRelease.sha256_hash}
                          <button
                            type="button"
                            className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700"
                            onClick={() => void navigator.clipboard.writeText(currentExtensionRelease.sha256_hash ?? "")}
                          >
                            Copy
                          </button>
                        </dd>
                      </div>
                    )}
                    {currentExtensionRelease.release_notes && (
                      <div className="sm:col-span-2">
                        <dt className="text-slate-500">Release notes</dt>
                        <dd className="text-slate-200">{currentExtensionRelease.release_notes}</dd>
                      </div>
                    )}
                  </dl>

                  {extensionDownloadMessage && <p className="mt-2 text-xs text-cyan-300">{extensionDownloadMessage}</p>}

                  <details className="mt-4">
                    <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200">Install instructions</summary>
                    <ol className="mt-2 space-y-1 pl-4 text-xs text-slate-300" style={{ listStyleType: "decimal" }}>
                      <li>Download the extension zip.</li>
                      <li>Extract it to a stable folder.</li>
                      <li>Open Chrome.</li>
                      <li>Go to chrome://extensions.</li>
                      <li>Turn on Developer Mode.</li>
                      <li>Click Load unpacked.</li>
                      <li>Select the extracted extension folder.</li>
                      <li>Open Bill Teaching Mode and confirm the extension is connected.</li>
                    </ol>
                  </details>
                </div>
              )}
            </section>
          )}

          {currentUser && currentUser.role === "viewer" && (
            <section className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
              <h2 className="text-base font-semibold text-slate-50">Extension Downloads</h2>
              <p className="mt-2 text-sm text-slate-400">You do not have permission to download the Bill Teaching Helper extension.</p>
            </section>
          )}

          {/* ── Admin Extension Releases ─────────────────────────────────────────── */}
          {currentUser?.role === "admin" && (
            <section id="extension-release-management" className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-base font-semibold text-slate-50">Extension Release Management</h2>
                <button
                  type="button"
                  className={BUTTON_SECONDARY}
                  onClick={() => void loadAdminExtensionReleases()}
                  disabled={adminExtensionReleasesLoading}
                >
                  {adminExtensionReleasesLoading ? "Loading..." : "Refresh"}
                </button>
              </div>

              {adminExtensionReleasesError && (
                <p className="mt-2 rounded-lg border border-rose-400/35 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">{adminExtensionReleasesError}</p>
              )}

              <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950/60 p-3">
                <p className="text-xs uppercase tracking-[0.14em] text-slate-400">Register New Extension Release</p>
                <p className="mt-1 text-[11px] text-slate-500">File must already be in the extension-packages directory on the server.</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <input
                    value={newExtensionVersionLabel}
                    onChange={(e) => setNewExtensionVersionLabel(e.target.value)}
                    placeholder="Version label (e.g. 1.2.0)"
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  />
                  <input
                    value={newExtensionFilename}
                    onChange={(e) => setNewExtensionFilename(e.target.value)}
                    placeholder="Filename (e.g. bill-teaching-helper-1.2.0.zip)"
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  />
                  <input
                    value={newExtensionReleaseNotes}
                    onChange={(e) => setNewExtensionReleaseNotes(e.target.value)}
                    placeholder="Release notes (optional)"
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 sm:col-span-2"
                  />
                </div>
                <button
                  type="button"
                  disabled={adminExtensionReleasesLoading}
                  onClick={() => void registerExtensionRelease()}
                  className="mt-3 rounded-lg bg-cyan-500 px-3 py-2 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Register extension release
                </button>
              </div>

              {adminExtensionReleases.length > 0 && (
                <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                  <p className="mb-2 text-xs uppercase tracking-[0.14em] text-slate-400">All Extension Releases</p>
                  <table className="min-w-full text-left text-xs text-slate-200">
                    <thead className="text-slate-500">
                      <tr>
                        <th className="py-1 pr-3">Version</th>
                        <th className="py-1 pr-3">Status</th>
                        <th className="py-1 pr-3">File</th>
                        <th className="py-1 pr-3">SHA-256</th>
                        <th className="py-1 pr-3">Downloads</th>
                        <th className="py-1 pr-3">Released</th>
                        <th className="py-1">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {adminExtensionReleases.map((rel) => (
                        <tr key={rel.id} className="border-t border-slate-800/70">
                          <td className="py-1 pr-3 font-semibold">{rel.version_label}</td>
                          <td className="py-1 pr-3">
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                                rel.status === "current"
                                  ? "bg-emerald-500/20 text-emerald-300"
                                  : rel.status === "disabled"
                                    ? "bg-rose-500/20 text-rose-300"
                                    : rel.status === "deprecated"
                                      ? "bg-amber-500/20 text-amber-300"
                                      : "bg-slate-700 text-slate-300"
                              }`}
                            >
                              {rel.status}
                            </span>
                          </td>
                          <td className="py-1 pr-3 font-mono text-[10px] text-slate-400">{rel.file_name}</td>
                          <td className="py-1 pr-3 font-mono text-[10px] text-slate-500" title={rel.sha256_hash ?? ""}>
                            {rel.sha256_hash ? rel.sha256_hash.slice(0, 12) + "…" : "—"}
                          </td>
                          <td className="py-1 pr-3">{rel.download_count}</td>
                          <td className="py-1 pr-3 text-slate-400">{new Date(rel.released_at).toLocaleDateString()}</td>
                          <td className="py-1">
                            <div className="flex gap-2">
                              {rel.status !== "current" && rel.status !== "disabled" && (
                                <button
                                  type="button"
                                  disabled={adminExtensionReleasesLoading}
                                  onClick={() => void markExtensionReleaseCurrent(rel.id)}
                                  className="rounded bg-cyan-600 px-2 py-0.5 text-[10px] font-semibold text-white hover:bg-cyan-500 disabled:opacity-50"
                                >
                                  Mark current
                                </button>
                              )}
                              {rel.status !== "disabled" && (
                                <button
                                  type="button"
                                  disabled={adminExtensionReleasesLoading}
                                  onClick={() => void disableExtensionRelease(rel.id)}
                                  className="rounded bg-rose-700 px-2 py-0.5 text-[10px] font-semibold text-white hover:bg-rose-600 disabled:opacity-50"
                                >
                                  Disable
                                </button>
                              )}
                              <button
                                type="button"
                                disabled={adminExtensionReleasesLoading || extensionDownloadBusy}
                                onClick={() => void downloadCurrentExtension(rel.id)}
                                className="rounded bg-slate-700 px-2 py-0.5 text-[10px] font-semibold text-slate-200 hover:bg-slate-600 disabled:opacity-50"
                              >
                                Download
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {/* ── Admin Worker Releases ─────────────────────────────────────────────── */}
          {currentUser?.role === "admin" && (
            <section className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-base font-semibold text-slate-50">Worker Release Management</h2>
                <button
                  type="button"
                  className={BUTTON_SECONDARY}
                  onClick={() => void loadAdminWorkerReleases()}
                  disabled={adminWorkerReleasesLoading}
                >
                  {adminWorkerReleasesLoading ? "Loading..." : "Refresh"}
                </button>
              </div>

              {adminWorkerReleasesError && (
                <p className="mt-2 rounded-lg border border-rose-400/35 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">{adminWorkerReleasesError}</p>
              )}

              {/* Register new release */}
              <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950/60 p-3">
                <p className="text-xs uppercase tracking-[0.14em] text-slate-400">Register New Release</p>
                <p className="mt-1 text-[11px] text-slate-500">File must already be in the worker-packages directory on the server.</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <input
                    value={newReleaseVersion}
                    onChange={(e) => setNewReleaseVersion(e.target.value)}
                    placeholder="Version (e.g. 0.4.0)"
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  />
                  <input
                    value={newReleaseFilename}
                    onChange={(e) => setNewReleaseFilename(e.target.value)}
                    placeholder="Filename (e.g. bill-worker-0.4.0.zip)"
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  />
                  <input
                    value={newReleaseNotes}
                    onChange={(e) => setNewReleaseNotes(e.target.value)}
                    placeholder="Release notes (optional)"
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 sm:col-span-2"
                  />
                  <select
                    value={newReleaseChannel}
                    onChange={(e) => setNewReleaseChannel(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  >
                    <option value="stable">stable</option>
                    <option value="optional">optional</option>
                    <option value="required">required</option>
                  </select>
                </div>
                <button
                  type="button"
                  disabled={adminWorkerReleasesLoading}
                  onClick={() => void registerWorkerRelease()}
                  className="mt-3 rounded-lg bg-cyan-500 px-3 py-2 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Register release
                </button>
              </div>

              {/* Releases table */}
              {adminWorkerReleases.length > 0 && (
                <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                  <p className="mb-2 text-xs uppercase tracking-[0.14em] text-slate-400">All Releases</p>
                  <table className="min-w-full text-left text-xs text-slate-200">
                    <thead className="text-slate-500">
                      <tr>
                        <th className="py-1 pr-3">Version</th>
                        <th className="py-1 pr-3">Status</th>
                        <th className="py-1 pr-3">File</th>
                        <th className="py-1 pr-3">SHA-256</th>
                        <th className="py-1 pr-3">Downloads</th>
                        <th className="py-1 pr-3">Uploaded</th>
                        <th className="py-1">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {adminWorkerReleases.map((rel) => (
                        <tr key={rel.id} className="border-t border-slate-800/70">
                          <td className="py-1 pr-3 font-semibold">{rel.version}</td>
                          <td className="py-1 pr-3">
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                                rel.status === "current"
                                  ? "bg-emerald-500/20 text-emerald-300"
                                  : rel.status === "disabled"
                                    ? "bg-rose-500/20 text-rose-300"
                                    : rel.status === "deprecated"
                                      ? "bg-amber-500/20 text-amber-300"
                                      : "bg-slate-700 text-slate-300"
                              }`}
                            >
                              {rel.status}
                            </span>
                          </td>
                          <td className="py-1 pr-3 font-mono text-[10px] text-slate-400">{rel.package_filename}</td>
                          <td className="py-1 pr-3 font-mono text-[10px] text-slate-500" title={rel.package_sha256 ?? ""}>
                            {rel.package_sha256 ? rel.package_sha256.slice(0, 12) + "…" : "—"}
                          </td>
                          <td className="py-1 pr-3">{rel.download_count}</td>
                          <td className="py-1 pr-3 text-slate-400">{new Date(rel.upload_time).toLocaleDateString()}</td>
                          <td className="py-1">
                            <div className="flex gap-2">
                              {rel.status !== "current" && rel.status !== "disabled" && (
                                <button
                                  type="button"
                                  disabled={adminWorkerReleasesLoading}
                                  onClick={() => void markReleaseCurrent(rel.id)}
                                  className="rounded bg-cyan-600 px-2 py-0.5 text-[10px] font-semibold text-white hover:bg-cyan-500 disabled:opacity-50"
                                >
                                  Mark current
                                </button>
                              )}
                              {rel.status !== "disabled" && (
                                <button
                                  type="button"
                                  disabled={adminWorkerReleasesLoading}
                                  onClick={() => void disableRelease(rel.id)}
                                  className="rounded bg-rose-700 px-2 py-0.5 text-[10px] font-semibold text-white hover:bg-rose-600 disabled:opacity-50"
                                >
                                  Disable
                                </button>
                              )}
                              <button
                                type="button"
                                disabled={adminWorkerReleasesLoading || workerDownloadBusy}
                                onClick={() => void downloadCurrentWorker(rel.id)}
                                className="rounded bg-slate-700 px-2 py-0.5 text-[10px] font-semibold text-slate-200 hover:bg-slate-600 disabled:opacity-50"
                              >
                                Download
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
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
                onStartTeaching={startTeachingFromCommandCenter}
              />

              {isAdminUser && extensionLearningVisible && (
                <section className="rounded-2xl border border-cyan-500/25 bg-slate-900/80 p-5 shadow-lg shadow-cyan-950/20">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">Extension Learning Session</p>
                      <h2 className="mt-1 text-lg font-semibold text-slate-50">Review captured extension learning</h2>
                    </div>
                    <div className="flex flex-wrap gap-2 text-[11px] font-semibold">
                      <span className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-1 text-cyan-100">Extension status: {extensionLearningConnectionStatus}</span>
                      <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200">Worker status: {extensionLearningWorkerStatus}</span>
                    </div>
                  </div>

                  <p className="mt-3 max-w-4xl text-sm text-slate-300">
                    Bill is receiving extension learning events, but the worker is offline. You can review captured learning now. Start the worker to open full Teaching Mode or test the workflow.
                  </p>

                  <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto_auto]">
                    <label className="block">
                      <span className="mb-1 block text-xs uppercase tracking-[0.16em] text-slate-400">Teaching session ID</span>
                      <input
                        value={extensionLearningSessionId}
                        onChange={(event) => setExtensionLearningSessionId(event.target.value)}
                        placeholder="Paste the active session id"
                        className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400/60"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => void startExtensionLearningPoll(extensionLearningSessionId)}
                      disabled={!extensionLearningSessionId.trim()}
                      className="self-end rounded-xl bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Load captured steps
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        stopExtensionLearningPoll();
                        setExtensionLearningState(null);
                        setExtensionLearningSessionId("");
                      }}
                      className="self-end rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-semibold text-slate-200"
                    >
                      Clear
                    </button>
                  </div>

                  {extensionLearningSession ? (
                    <>
                      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
                        <section className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-xs uppercase tracking-[0.16em] text-cyan-300">Captured summary</p>
                            <span className="text-[11px] text-slate-400">Extension events: {extensionLearningSession.extensionEventCount ?? 0}</span>
                          </div>
                          <div className="mt-3 space-y-2 text-sm text-slate-300">
                            <p><span className="text-slate-400">Latest extension event:</span> {summarizeExtensionEvent(extensionLearningLatestEvent)}</p>
                            <p><span className="text-slate-400">Captured steps:</span> {extensionLearningStepStatusSummary.total} total, {extensionLearningStepStatusSummary.runnable} runnable, {extensionLearningStepStatusSummary.manualOnly} manual-only, {extensionLearningStepStatusSummary.needsClarification} need clarification</p>
                            <p><span className="text-slate-400">Bill summary:</span> {extensionLearningSession.workflowSummary || "Waiting for more learning"}</p>
                          </div>
                        </section>

                        <section className={`rounded-2xl border p-4 ${extensionLearningReadiness?.toneClass || "border-slate-800 bg-slate-950/60 text-slate-200"}`}>
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-xs uppercase tracking-[0.16em]">Readiness</p>
                            <span className="text-[11px] font-semibold">{extensionLearningReadiness?.label || "Unknown"}</span>
                          </div>
                          <p className="mt-2 text-sm font-semibold">{extensionLearningReadiness?.label || "Unknown"}</p>
                          <ul className="mt-2 space-y-1 text-xs">
                            {(extensionLearningReadiness?.reasons ?? ["Waiting for extension events."]).slice(0, 3).map((reason, index) => (
                              <li key={`extension-readiness-${index}`}>{reason}</li>
                            ))}
                          </ul>
                          <div className="mt-3 rounded-lg border border-slate-200/10 bg-slate-950/30 px-3 py-2 text-xs text-slate-300">
                            <p><span className="text-slate-400">URL:</span> {extensionLearningSession.pageContextSnapshot?.url || "Waiting for page context"}</p>
                            <p><span className="text-slate-400">Buttons:</span> {(extensionLearningSession.pageContextSnapshot?.visible_buttons?.length ?? 0) || (extensionLearningSession.pageContextSnapshot?.buttons?.length ?? 0)}</p>
                            <p><span className="text-slate-400">Fields:</span> {(extensionLearningSession.pageContextSnapshot?.visible_inputs?.length ?? 0) || (extensionLearningSession.pageContextSnapshot?.inputs?.length ?? 0)}</p>
                            <p><span className="text-slate-400">Links:</span> {(extensionLearningSession.pageContextSnapshot?.visible_links?.length ?? 0) || (extensionLearningSession.pageContextSnapshot?.links?.length ?? 0)}</p>
                          </div>
                        </section>
                      </div>

                      <div className="mt-4 space-y-3">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-xs uppercase tracking-[0.16em] text-slate-400">Captured steps</p>
                          <span className="text-xs text-slate-400">Source: Chrome extension</span>
                        </div>
                        <div className="space-y-3">
                          {extensionLearningSession.steps.map((step) => (
                            <TeachingStepCard
                              key={step.id}
                              step={step}
                              stepNumber={step.order}
                              status={explainStepStatus(step)}
                              formatObservedAction={formatObservedAction}
                              compact
                            />
                          ))}
                        </div>
                      </div>
                    </>
                  ) : extensionLearningSessionId.trim() ? (
                    <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-3 text-sm text-slate-300">
                      No extension steps have been loaded for this session yet.
                    </div>
                  ) : null}
                </section>
              )}

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
                currentUserRole={currentUser?.role ?? null}
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
                selectedWorkflowRunnable={selectedWorkflowRunnable}
                selectedWorkflowBlockingReason={selectedWorkflowBlockingReason}
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
                knowledgeEntries={knowledgeEntries}
                knowledgeLoading={knowledgeLoading}
                knowledgeError={knowledgeError}
                knowledgeActionBusyKey={knowledgeActionBusyKey}
                knowledgeActionFeedback={knowledgeActionFeedback}
                onRefreshKnowledge={() => void loadKnowledgePanels()}
                onCreateKnowledge={(payload) => void createKnowledgeEntry(payload)}
                onUpdateKnowledge={(knowledgeId, payload) => void updateKnowledgeEntry(knowledgeId, payload)}
                onArchiveKnowledge={(knowledgeId) => void archiveKnowledgeEntry(knowledgeId)}
                onActivateKnowledge={(knowledgeId) => void activateKnowledgeEntry(knowledgeId)}
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
        <div className="fixed inset-3 z-[70] flex flex-col gap-3 pointer-events-none">
          <button
            type="button"
            onClick={() => {
              setTeachingOverlayOpen(true);
              logTeachOverlay("manual overlay open requested", { session_id: guidedTeachingSession.sessionId });
            }}
            className="pointer-events-auto self-start rounded-full border border-cyan-400/40 bg-cyan-500/15 px-4 py-2 text-sm font-semibold text-cyan-100 shadow-lg shadow-cyan-950/40 hover:bg-cyan-500/25"
          >
            Start Teaching
          </button>

          {teachingStartupState && teachingStartupState.status !== "active" && (
            <section
              className={`pointer-events-auto w-full max-w-[min(42rem,calc(100vw-1.5rem))] rounded-2xl border p-4 text-slate-100 shadow-2xl backdrop-blur ${
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
                      ? `Launching Bill Teaching Browser on ${teachingStartupState.target_machine_name || "selected worker"}`
                      : `Teaching browser failed for ${teachingStartupState.workflow_name}`}
                  </h3>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {teachingStartupState.status === "browser_opening"
                      ? "Waiting for browser connection and capture readiness confirmation..."
                      : "Bill could not open the teaching browser. Restart the worker and try again."}
                  </p>
                  <p className="mt-1 text-[11px] text-cyan-100/90">
                    Use only the Bill Teaching Browser for runnable workflow capture.
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
            <section className="pointer-events-auto flex min-h-0 flex-1 flex-col overflow-hidden rounded-3xl border border-cyan-400/30 bg-slate-950/95 text-slate-100 shadow-2xl shadow-slate-950/60 backdrop-blur">
              <header className="flex items-start justify-between gap-3 border-b border-slate-800 px-4 py-4">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">Teaching Mode Active</p>
                  <h2 className="mt-1 text-lg font-semibold text-white">{guidedTeachingSession.workflowName}</h2>
                  <p className="mt-1 text-xs text-slate-300">Teach only inside the Bill Teaching Browser. Do not use normal Chrome for runnable workflows.</p>
                  <p className="mt-2 text-[11px] text-slate-300">
                    Worker {teachingStartupState?.target_machine_name || "selected worker"} • Session {shortEntityId(guidedTeachingSession.sessionId)} • Draft {shortEntityId(teachingSessionDraftId || teachingStartupState?.draft_id)}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-400">
                    Browser: Connected • Capture: {teachingCaptureReady ? "Ready" : "Not Ready"} • Last captured: {lastCapturedActionSummary}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-400">
                    Actions: {teachingObservedActionCount} observed • Executable: {teachingExecutableActionCount} • Last callback {toDisplayTime(teachingStartupState?.teaching_session?.last_extension_event?.captured_at as string | undefined)}
                  </p>
                  {!teachingCaptureReady && (
                    <p className="mt-2 rounded-md border border-amber-400/40 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-100">
                      Capture is not ready yet. If the action counter does not move after you click or type in Bill Teaching Browser, stop teaching and contact admin.
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setTeachingOverlayOpen(false)}
                    className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-300 hover:border-slate-500 hover:text-white"
                  >
                    Cancel / End Session
                  </button>
                  <button
                    type="button"
                    onClick={() => void reviewGuidedTeachingSession()}
                    disabled={guidedTeachingBusy || guidedTeachingSession.status === "review" || guidedTeachingSession.status === "approved"}
                    className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-100 hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Finish Teaching
                  </button>
                  <button
                    type="button"
                    onClick={() => void approveGuidedTeachingSession()}
                    disabled={guidedTeachingBusy}
                    className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-100 hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Approve Draft
                  </button>
                  <button
                    type="button"
                    onClick={() => void runGuidedTeachingWorkflowNow()}
                    disabled={guidedTeachingRunNowBusy || !guidedTeachingEffectiveReadiness?.runnable}
                    className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-100 hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {guidedTeachingRunNowBusy ? "Running..." : "Run Test"}
                  </button>
                </div>
              </header>

              <div className="grid min-h-0 flex-1 gap-4 overflow-hidden px-4 py-4 lg:grid-cols-[minmax(0,1.65fr)_minmax(320px,0.95fr)]">
                <div className="flex min-h-0 flex-col gap-4 overflow-hidden">
                  <section className="rounded-2xl border border-cyan-800/60 bg-cyan-950/30 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs uppercase tracking-[0.16em] text-cyan-300">Teaching Coach</p>
                      <span className={`rounded-full border px-2 py-1 text-[11px] font-semibold ${guidedTeachingEffectiveReadiness?.runnable ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-100" : "border-amber-400/40 bg-amber-500/10 text-amber-100"}`}>
                        {guidedTeachingEffectiveReadiness?.runnable ? "Ready to test" : "Still teaching"}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-2 text-sm">
                      <div className="rounded-lg border border-cyan-700/40 bg-slate-950/40 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.14em] text-cyan-200/80">Current phase</p>
                        <p className="mt-1 font-semibold text-cyan-50">{teachingCoach.phase}</p>
                      </div>
                      <div className="rounded-lg border border-cyan-700/40 bg-slate-950/40 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.14em] text-cyan-200/80">One short instruction</p>
                        <p className="mt-1 text-cyan-50">{teachingCoach.guidance}</p>
                      </div>
                      <div className="rounded-lg border border-emerald-700/40 bg-slate-950/40 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.14em] text-emerald-200/80">Next recommended action</p>
                        <p className="mt-1 text-emerald-50">{teachingCoach.nextAction}</p>
                      </div>
                      <div className="rounded-lg border border-amber-700/40 bg-slate-950/40 px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.14em] text-amber-200/80">Example phrase</p>
                        <p className="mt-1 text-amber-50">{teachingCoach.examplePhrase}</p>
                      </div>
                    </div>
                  </section>

                  <section className="min-h-0 rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Conversation</p>
                      <span className="text-xs text-slate-400">Use only Bill Teaching Browser tabs</span>
                    </div>
                    <div className="mt-2 flex min-h-0 flex-col gap-3">
                      {teachingVoiceError && (
                        <p className="rounded-md border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">
                          {teachingVoiceError}
                        </p>
                      )}
                      <div className="max-h-52 space-y-2 overflow-auto pr-1 text-sm leading-5">
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
                        className="min-h-24 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400/60"
                      />
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => void submitGuidedTeachingMessage()}
                          disabled={guidedTeachingBusy || !guidedTeachingInput.trim()}
                          className="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
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
                          className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                            isListening
                              ? "border border-rose-400/50 bg-rose-500/20 text-rose-100"
                              : "border border-indigo-400/40 bg-indigo-500/15 text-indigo-100 hover:bg-indigo-500/25"
                          }`}
                          disabled={!voiceSupported}
                        >
                          {isListening ? "Stop Listening" : "Speak to Bill"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void continueGuidedTeachingSession()}
                          disabled={guidedTeachingBusy}
                          className="rounded-lg border border-slate-600 px-4 py-2 text-sm font-semibold text-slate-200 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Continue Teaching
                        </button>
                        <button
                          type="button"
                          onClick={() => void reviewGuidedTeachingSession()}
                          disabled={guidedTeachingBusy || guidedTeachingSession.status === "review" || guidedTeachingSession.status === "approved"}
                          className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm font-semibold text-amber-100 hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Review
                        </button>
                      </div>
                    </div>
                  </section>

                  <section className="min-h-0 rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Steps</p>
                      <span className="text-xs text-slate-400">{guidedTeachingSession.steps.length} captured</span>
                    </div>
                    <div className="mt-2 max-h-[36vh] space-y-2 overflow-y-auto pr-1">
                      {guidedTeachingSession.steps.length === 0 ? (
                        <div className="rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-3 text-sm text-slate-300">
                          Step cards are ready. As you teach, Bill will add summarized steps here.
                        </div>
                      ) : (
                        guidedTeachingSession.steps.map((step) => {
                          const status = explainStepStatus(step);
                          const isEditing = editingStepId === step.id;
                          return (
                            <article key={step.id} className="space-y-3 rounded-xl border border-slate-700 bg-slate-950/70 p-3 text-sm">
                              <TeachingStepCard
                                step={step}
                                stepNumber={step.order}
                                status={status}
                                formatObservedAction={formatObservedAction}
                              />

                              {isEditing ? (
                                <div className="space-y-2">
                                  <input
                                    value={editingStepState.title}
                                    onChange={(event) => setEditingStepState((current) => ({ ...current, title: event.target.value }))}
                                    className="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1.5 text-sm text-white"
                                    placeholder="Step title"
                                  />
                                  <textarea
                                    value={editingStepState.employeeExplanation}
                                    onChange={(event) => setEditingStepState((current) => ({ ...current, employeeExplanation: event.target.value }))}
                                    className="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1.5 text-xs text-slate-100"
                                    placeholder="What employee did"
                                  />
                                  <textarea
                                    value={editingStepState.billSummary}
                                    onChange={(event) => setEditingStepState((current) => ({ ...current, billSummary: event.target.value }))}
                                    className="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1.5 text-xs text-slate-100"
                                    placeholder="What Bill thinks"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => setEditingAdvancedDetailsOpen((current) => !current)}
                                    className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-200"
                                  >
                                    {editingAdvancedDetailsOpen ? "Hide Advanced Details" : "Advanced Details"}
                                  </button>
                                  {editingAdvancedDetailsOpen && (
                                    <>
                                      <input
                                        value={editingStepState.decisionRules}
                                        onChange={(event) => setEditingStepState((current) => ({ ...current, decisionRules: event.target.value }))}
                                        className="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1.5 text-xs text-slate-100"
                                        placeholder="Decision rules (semicolon separated)"
                                      />
                                      <input
                                        value={editingStepState.exceptions}
                                        onChange={(event) => setEditingStepState((current) => ({ ...current, exceptions: event.target.value }))}
                                        className="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1.5 text-xs text-slate-100"
                                        placeholder="Exceptions (semicolon separated)"
                                      />
                                      <input
                                        value={editingStepState.requiredInputs}
                                        onChange={(event) => setEditingStepState((current) => ({ ...current, requiredInputs: event.target.value }))}
                                        className="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1.5 text-xs text-slate-100"
                                        placeholder="Required inputs (comma separated)"
                                      />
                                    </>
                                  )}
                                </div>
                              ) : null}

                              <div className="mt-2 flex flex-wrap gap-2">
                                {isEditing ? (
                                  <>
                                    <button
                                      type="button"
                                      onClick={() => void handleSaveEditStep(step.id)}
                                      disabled={guidedTeachingBusy}
                                      className="rounded border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      Save
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => handleCancelEditStep()}
                                      disabled={guidedTeachingBusy}
                                      className="rounded border border-slate-600 px-3 py-2 text-xs font-semibold text-slate-200"
                                    >
                                      Cancel
                                    </button>
                                  </>
                                ) : (
                                  <>
                                    <button
                                      type="button"
                                      onClick={() => void confirmGuidedTeachingStep(step.id)}
                                      disabled={guidedTeachingBusy || step.confirmed}
                                      className="rounded border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      Confirm
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => handleEditStep(step)}
                                      disabled={guidedTeachingBusy}
                                      className="rounded border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      Fix Step
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => handleAddDetail(step)}
                                      disabled={guidedTeachingBusy}
                                      className="rounded border border-slate-600 px-3 py-2 text-xs font-semibold text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      Add Detail
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        if (window.confirm("Delete this step?")) {
                                          void handleDeleteStep(step);
                                        }
                                      }}
                                      disabled={guidedTeachingBusy}
                                      className="rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      Remove
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => void handleRedoStep(step)}
                                      disabled={guidedTeachingBusy}
                                      className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      Redo
                                    </button>
                                  </>
                                )}
                              </div>
                            </article>
                          );
                        })
                      )}
                    </div>
                  </section>

                  <details className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                    <summary className="cursor-pointer text-xs uppercase tracking-[0.16em] text-slate-400">Advanced details</summary>
                    <div className="mt-2 space-y-2 text-xs text-slate-300">
                      <p>Session ID: {guidedTeachingSession.sessionId || "n/a"}</p>
                      <p>Draft ID: {teachingSessionDraftId || teachingStartupState?.draft_id || "Draft ID pending"}</p>
                      <p>Task ID: {teachingOverlayTaskId || teachingStartupState?.task_id || "n/a"}</p>
                      <p>Startup status: {teachingStartupState?.status || "n/a"}</p>
                      <p>Worker UUID: {teachingStartupState?.target_machine_uuid || "n/a"}</p>
                      <pre className="max-h-56 overflow-auto rounded-md border border-slate-700 bg-slate-950/80 p-2 text-[11px] text-slate-200">
                        {JSON.stringify(guidedTeachingSession.pageContextSnapshot ?? {}, null, 2)}
                      </pre>
                    </div>
                  </details>
                </div>

                <aside className="flex min-h-0 flex-col gap-4 overflow-y-auto lg:sticky lg:top-0">
                  <section className="rounded-2xl border border-emerald-800/60 bg-emerald-950/25 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs uppercase tracking-[0.16em] text-emerald-300">Captured So Far</p>
                      <span className="text-[11px] text-emerald-100/80">Compact summary</span>
                    </div>
                    <div className="mt-3 space-y-2 text-xs text-emerald-50">
                      <p><span className="text-emerald-200/80">Current page:</span> {observedCurrentPage || "Waiting for page"}</p>
                      <p><span className="text-emerald-200/80">Starting page:</span> {canonicalStartUrl || "Not confirmed yet"}</p>
                      <p><span className="text-emerald-200/80">Suggested starting page:</span> {suggestedStartUrl || "None"}</p>
                      <p><span className="text-emerald-200/80">Capture readiness:</span> {teachingCaptureReady ? "Ready" : "Not Ready"}</p>
                      <p><span className="text-emerald-200/80">Observed actions:</span> {teachingObservedActionCount}</p>
                      <p><span className="text-emerald-200/80">Executable actions:</span> {teachingExecutableActionCount}</p>
                      <p><span className="text-emerald-200/80">Observation Mode (normal Chrome):</span> Not used for runnable workflows</p>
                      <p><span className="text-emerald-200/80">Detected controls:</span> {capturedButtons.length + capturedFields.length + capturedLinks.length} total</p>
                      <p><span className="text-emerald-200/80">Top controls:</span> {capturedButtons.slice(0, 2).join(", ") || "None yet"}</p>
                      <p><span className="text-emerald-200/80">Steps captured:</span> {stepStatusSummary.runnable} runnable, {stepStatusSummary.manualOnly} manual-only, {stepStatusSummary.needsClarification} need clarification</p>
                      {!canonicalStartUrl && suggestedStartUrl ? (
                        <button
                          type="button"
                          onClick={() => void confirmCurrentPageAsStartingPage()}
                          disabled={guidedTeachingBusy}
                          className="inline-flex items-center rounded-md border border-emerald-300/40 bg-emerald-500/15 px-3 py-1.5 text-[11px] font-semibold text-emerald-100 transition hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Use current page as starting page
                        </button>
                      ) : null}
                    </div>
                    <details className="mt-3 rounded-lg border border-emerald-400/20 bg-slate-950/30 px-3 py-2">
                      <summary className="cursor-pointer text-[11px] uppercase tracking-[0.14em] text-emerald-100/80">Show technical info</summary>
                      <div className="mt-2 space-y-2 text-xs text-emerald-100">
                        <p>Workflow: {guidedTeachingSession.workflowName || "Untitled"}</p>
                        <p>Purpose: {guidedTeachingSession.workflowSummary || "Needs clarification"}</p>
                        <p>Buttons: {capturedButtons.slice(0, 5).join(", ") || "None yet"}</p>
                        <p>Fields: {capturedFields.slice(0, 5).join(", ") || "None yet"}</p>
                        <p>Links: {capturedLinks.slice(0, 5).join(", ") || "None yet"}</p>
                      </div>
                    </details>
                  </section>

                  <section className={`rounded-2xl border p-4 ${employeeReadiness.toneClass}`}>
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs uppercase tracking-[0.16em]">Readiness</p>
                      <span className="text-[11px] font-semibold">
                        {employeeReadiness.label === "Ready to test" ? "Ready to test" : employeeReadiness.label === "Almost ready" ? "Almost ready" : "Not ready yet"}
                      </span>
                    </div>
                    <p className="mt-2 text-sm font-semibold">{employeeReadiness.label}</p>
                    <ul className="mt-2 space-y-1 text-xs">
                      {employeeReadiness.reasons.slice(0, 3).map((reason, index) => (
                        <li key={`employee-readiness-${index}`}>{reason}</li>
                      ))}
                    </ul>
                    <div className="mt-3 rounded-lg border border-slate-200/10 bg-slate-950/30 px-3 py-2 text-xs">
                      <p className="font-semibold text-white">Top missing items</p>
                      <ul className="mt-1 list-disc space-y-1 pl-4 text-slate-100/90">
                        {(guidedTeachingEffectiveReadiness?.blocking_reasons ?? []).slice(0, 3).map((reason, index) => (
                          <li key={`readiness-block-${index}`}>{reason}</li>
                        ))}
                        {(!guidedTeachingEffectiveReadiness?.blocking_reasons || guidedTeachingEffectiveReadiness.blocking_reasons.length === 0) && (
                          <li>No blocking items.</li>
                        )}
                      </ul>
                    </div>
                  </section>

                  <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                    <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Status</p>
                    <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
                      <span className="rounded border border-cyan-400/40 bg-cyan-500/10 px-2 py-1">Workflow: {guidedTeachingSession.status}</span>
                      <span className="rounded border border-emerald-400/40 bg-emerald-500/10 px-2 py-1">Runnable: {guidedTeachingEffectiveReadiness?.runnable ? "Yes" : "No"}</span>
                      <span className="rounded border border-amber-400/40 bg-amber-500/10 px-2 py-1">Warnings: {guidedTeachingWarnings.length}</span>
                    </div>
                    {guidedTeachingRunNowMessage && (
                      <p className="mt-3 rounded-md border border-cyan-400/40 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-100">
                        {guidedTeachingRunNowMessage}
                      </p>
                    )}
                    {guidedTeachingApprovalMessage && (
                      <p className="mt-3 rounded-md border border-emerald-400/40 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100">
                        {guidedTeachingApprovalMessage}
                      </p>
                    )}
                  </section>

                  <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Workflow SOP</p>
                      <span className="text-[11px] text-slate-400">
                        {guidedTeachingSopRecord ? `Generated ${new Date(guidedTeachingSopRecord.generated_at).toLocaleString()}` : "Not generated"}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void generateGuidedTeachingSop()}
                        disabled={guidedTeachingSopBusy}
                        className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {guidedTeachingSopBusy ? "Generating..." : "Generate SOP"}
                      </button>
                      <button
                        type="button"
                        onClick={() => void copyGuidedTeachingSop()}
                        disabled={!guidedTeachingSopRecord?.markdown}
                        className="rounded-lg border border-slate-600 px-3 py-2 text-xs font-semibold text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Copy
                      </button>
                      <button
                        type="button"
                        onClick={() => downloadGuidedTeachingSop()}
                        disabled={!guidedTeachingSopRecord?.markdown}
                        className="rounded-lg border border-slate-600 px-3 py-2 text-xs font-semibold text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Download .md
                      </button>
                    </div>
                    {guidedTeachingSopError && (
                      <p className="mt-3 rounded-md border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">
                        {guidedTeachingSopError}
                      </p>
                    )}
                    {guidedTeachingSopRecord?.markdown && (
                      <details className="mt-3 rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2" open>
                        <summary className="cursor-pointer text-[11px] uppercase tracking-[0.14em] text-slate-400">Preview SOP</summary>
                        <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-slate-100">
                          {guidedTeachingSopRecord.markdown}
                        </pre>
                      </details>
                    )}
                  </section>
                </aside>
              </div>

              <footer className="border-t border-slate-800 bg-slate-950/90 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-500">Actions</span>
                  <button
                    type="button"
                    onClick={() => setTeachingOverlayOpen(true)}
                    className="rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-3 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-500/20"
                  >
                    Start Teaching
                  </button>
                  <button
                    type="button"
                    onClick={() => void confirmGuidedTeachingStep(latestTeachingStep?.id ?? "")}
                    disabled={!latestTeachingStep || guidedTeachingBusy || latestTeachingStep.confirmed}
                    className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Confirm Step
                  </button>
                  <button
                    type="button"
                    onClick={() => latestTeachingStep ? handleEditStep(latestTeachingStep) : undefined}
                    disabled={!latestTeachingStep || guidedTeachingBusy}
                    className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-sm font-semibold text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Fix Step
                  </button>
                  <button
                    type="button"
                    onClick={() => void reviewGuidedTeachingSession()}
                    disabled={guidedTeachingBusy || guidedTeachingSession.status === "review" || guidedTeachingSession.status === "approved"}
                    className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm font-semibold text-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Finish Teaching
                  </button>
                  <button
                    type="button"
                    onClick={() => void runGuidedTeachingWorkflowNow()}
                    disabled={guidedTeachingRunNowBusy || !guidedTeachingEffectiveReadiness?.runnable}
                    className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-2 text-sm font-semibold text-sky-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Run Test
                  </button>
                  <button
                    type="button"
                    onClick={() => setTeachingOverlayOpen(false)}
                    className="rounded-lg border border-slate-700 px-3 py-2 text-sm font-semibold text-slate-300 hover:border-slate-500 hover:text-white"
                  >
                    Cancel / End Session
                  </button>
                </div>
              </footer>
            </section>
          ) : null}
        </div>
      ) : null}
    </main>
  );
}
