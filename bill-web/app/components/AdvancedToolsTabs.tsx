"use client";

import { useState } from "react";
import RecoveryPanel from "./RecoveryPanel";
import RecoveryAnalyticsPanel from "./RecoveryAnalyticsPanel";
import BillVoiceControls from "./BillVoiceControls";
import { BatchRunnerTab } from "./BatchRunnerTab";
import type { useBillVoice } from "../hooks/useBillVoice";

type BillVoiceHandle = ReturnType<typeof useBillVoice>;

// ΓöÇΓöÇ Types mirrored from page.tsx ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

interface WorkflowRecord {
  workflow_name: string;
  description: string;
}

interface Machine {
  machine_uuid?: string;
  machine_name?: string;
  worker_name?: string;
  status?: string;
  online?: boolean;
}

interface Task {
  id?: string;
  status?: string;
  payload?: { task_type?: string; [key: string]: unknown };
  assigned_machine_uuid?: string | null;
  error?: string | null;
  created_at?: string;
  result_json?: { downloads?: Array<{ filename?: string; local_path?: string }>; [key: string]: unknown };
}

interface BrainAuditEntry {
  timestamp?: string;
  original_user_text?: string;
  interpreted_intent?: string;
  selected_workflow?: string | null;
  selected_worker?: string | null;
  queued_task_id?: string | null;
  before_execution?: string;
  after_execution?: string;
}

interface WorkflowLearningDraft {
  draft_id: string;
  workflow_name: string;
  learning_path: string;
  goal: string;
  review_status: string;
  updated_at: string;
  steps: unknown[];
  teaching_complete?: boolean;
  execution_readiness?: {
    runnable?: boolean;
    has_start_url?: boolean;
    manual_action_count?: number;
    redacted_input_count?: number;
    blocking_reasons?: string[];
    warnings?: string[];
  };
  created_by_name?: string | null;
  last_updated_by_name?: string | null;
  approved_by_name?: string | null;
}

interface KnowledgeRecord {
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
}

interface WorkerRelease {
  id: string;
  version: string;
  upload_time: string;
  release_notes?: string | null;
  package_filename: string;
  package_sha256?: string | null;
  is_active: boolean;
  channel: string;
}

interface DeployWorkerStatus {
  machine_uuid: string;
  machine_name?: string | null;
  worker_version?: string | null;
  update_status?: string | null;
  update_target_version?: string | null;
  update_error?: string | null;
}

interface WorkerDeployStatus {
  active_release_version?: string | null;
  workers: DeployWorkerStatus[];
}

interface ActionFeedback {
  kind: "success" | "error";
  message: string;
  timestamp: string;
}

interface ChatEntry {
  role: "user" | "assistant";
  message: string;
  suggestedNextAction?: string;
}

// ΓöÇΓöÇ Helper constants ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

const BTN_SECONDARY =
  "rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-cyan-400/70 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50";
const BTN_PRIMARY =
  "rounded-lg bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50";
const BTN_DANGER =
  "rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-1.5 text-xs text-rose-200 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-40";
const BTN_GHOST =
  "rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-200 transition hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-40";

function toDisplayTime(v?: string): string {
  if (!v) return "-";
  const d = new Date(v);
  return isNaN(d.getTime()) ? v : d.toLocaleString();
}

function updateStatusClasses(status?: string | null): string {
  const s = (status ?? "").toLowerCase();
  if (s === "updated") return "bg-emerald-500/15 text-emerald-200 border border-emerald-400/30";
  if (s === "failed") return "bg-rose-500/15 text-rose-200 border border-rose-400/30";
  if (s === "downloading" || s === "installing") return "bg-sky-500/15 text-sky-200 border border-sky-400/30";
  if (s === "pending" || s === "restarting") return "bg-amber-500/15 text-amber-200 border border-amber-400/30";
  return "bg-slate-700/60 text-slate-400";
}

function shortTaskId(id?: string): string {
  if (!id) return "-";
  return id.length > 10 ? `${id.slice(0, 8)}ΓÇª` : id;
}

// ΓöÇΓöÇ Tab definitions ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

const TABS = [
  "Advanced Tools",
  "Batch Runner",
  "Recovery",
  "Analytics",
  "Voice",
  "Teach Bill",
  "Knowledge Center",
  "Extension Downloads",
  "Workflow Builder",
  "Audit Trail",
  "Settings",
] as const;
type TabName = (typeof TABS)[number];

// ΓöÇΓöÇ Props ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

interface AdvancedToolsTabsProps {
  apiBase: string;
  billVoice: BillVoiceHandle;
  currentUserRole?: "admin" | "teacher" | "runner" | "viewer" | null;

  // Audit
  auditEntries: BrainAuditEntry[];
  onRefreshAudit: () => void;
  auditError?: string;

  // Teach Bill
  learningPath: string;
  setLearningPath: (v: string) => void;
  learningWorkflowName: string;
  setLearningWorkflowName: (v: string) => void;
  learningGoal: string;
  setLearningGoal: (v: string) => void;
  learningSourceText: string;
  setLearningSourceText: (v: string) => void;
  learningBusyKey: string | null;
  learningFeedback: ActionFeedback | null;
  workflowDrafts: WorkflowLearningDraft[];
  expandedDraftId: string | null;
  setExpandedDraftId: (v: string | null) => void;
  onCreateDraft: () => void;
  onDeleteDraft: (id: string, name: string) => void;
  onUpdateDraftStatus: (id: string, status: string) => void;
  onStartTeachingSession: (id: string) => void;
  onTestDraft: (id: string) => void;
  onPublishDraft: (id: string) => void;
  teachingSessionDraftId: string | null;
  draftsError?: string;
  teachingTargetWorkerUuid: string;
  setTeachingTargetWorkerUuid: (v: string) => void;
  machines: Machine[];

  // Workflow Builder
  workflows: WorkflowRecord[];
  helperWorkflow: string;
  setHelperWorkflow: (v: string) => void;
  helperWorkerUuid: string;
  setHelperWorkerUuid: (v: string) => void;
  helperClientName: string;
  setHelperClientName: (v: string) => void;
  helperHouseholdName: string;
  setHelperHouseholdName: (v: string) => void;
  helperMaxClients: string;
  setHelperMaxClients: (v: string) => void;
  helperMaxPages: string;
  setHelperMaxPages: (v: string) => void;
  helperRetryFailedOnly: boolean;
  setHelperRetryFailedOnly: (v: boolean) => void;
  helperFreeText: string;
  setHelperFreeText: (v: string) => void;
  helperBusy: boolean;
  helperFeedback: ActionFeedback | null;
  onRunGuidedCommand: () => void;
  onRunFreeTextCommand: () => void;
  workflowsError?: string;

  // All tasks (for task list in settings)
  tasks: Task[];
  taskActionBusyKey: string | null;
  taskActionFeedback: ActionFeedback | null;
  onCancelTask: (id?: string) => void;
  onRetryTask: (task: Task) => void;
  selectedTask: Task | null;
  setSelectedTask: (t: Task | null) => void;
  loading: boolean;
  actionError: string | null;
  response: unknown | null;
  onCreateTestTask: () => void;
  onCreateScreenshotTask: () => void;
  onCreateVisibleWorkflowTask: () => void;
  onRunSmartSherpa: () => void;
  onRunWorkflow: (name: string) => void;
  selectedWorkflowRunnable: boolean;
  selectedWorkflowBlockingReason: string | null;
  targetMachineUuid: string;
  setTargetMachineUuid: (v: string) => void;

  // Worker Updates (Settings tab)
  workerReleases: WorkerRelease[];
  workerDeployStatus: WorkerDeployStatus | null;
  releaseUploadVersion: string;
  setReleaseUploadVersion: (v: string) => void;
  releaseUploadNotes: string;
  setReleaseUploadNotes: (v: string) => void;
  releaseUploadChannel: string;
  setReleaseUploadChannel: (v: string) => void;
  releaseUploadFile: File | null;
  setReleaseUploadFile: (f: File | null) => void;
  releaseUploadBusy: boolean;
  releaseBusyKey: string | null;
  releasesFeedback: ActionFeedback | null;
  deployBusy: boolean;
  deployForce: boolean;
  setDeployForce: (v: boolean) => void;
  deployIdleOnly: boolean;
  setDeployIdleOnly: (v: boolean) => void;
  onUploadRelease: () => void;
  onActivateRelease: (id: string) => void;
  onDeleteRelease: (id: string) => void;
  onDeployToWorkers: (uuids?: string[]) => void;
  onRefreshBrainPanels: () => void;

  // Chat history
  chatHistory: ChatEntry[];

  // Knowledge center
  knowledgeEntries: KnowledgeRecord[];
  knowledgeLoading: boolean;
  knowledgeError: string | null;
  knowledgeActionBusyKey: string | null;
  knowledgeActionFeedback: ActionFeedback | null;
  onRefreshKnowledge: () => void;
  onCreateKnowledge: (payload: {
    title: string;
    category: string;
    applies_to: string[];
    content: string;
    source_type: "manual" | "document" | "imported" | "system";
    tags: string[];
    status: "active" | "draft" | "archived";
    tenant_id?: string | null;
  }) => void;
  onUpdateKnowledge: (
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
  ) => void;
  onArchiveKnowledge: (knowledgeId: string) => void;
  onActivateKnowledge: (knowledgeId: string) => void;
}

// ΓöÇΓöÇ Component ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

export function AdvancedToolsTabs(props: AdvancedToolsTabsProps) {
  const [activeTab, setActiveTab] = useState<TabName>("Advanced Tools");

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/80 shadow-lg">
      {/* Tab strip */}
      <div className="flex flex-wrap gap-px overflow-hidden rounded-t-2xl border-b border-slate-800 bg-slate-950/50">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-3 text-xs font-medium transition ${
              activeTab === tab
                ? "border-b-2 border-cyan-400 bg-slate-900/80 text-cyan-300"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            {tab}
          </button>
        ))}
        <div className="ml-auto flex items-center pr-3">
          <span className="text-[11px] text-slate-600">
            {activeTab === "Advanced Tools" ? "Click a tab to access advanced tools" : ""}
          </span>
        </div>
      </div>

      {/* Tab content */}
      <div className="p-5">
        {activeTab === "Advanced Tools" && (
          <p className="text-sm text-slate-400">
            Advanced system tools and analytics. Click a tab above to access.
          </p>
        )}

        {activeTab === "Batch Runner" && (
          <BatchRunnerTab machines={props.machines} />
        )}

        {activeTab === "Recovery" && (
          <RecoveryPanel apiBase={props.apiBase} />
        )}

        {activeTab === "Analytics" && (
          <RecoveryAnalyticsPanel apiBase={props.apiBase} />
        )}

        {activeTab === "Voice" && (
          <BillVoiceControls voice={props.billVoice} />
        )}

        {activeTab === "Teach Bill" && (
          <TeachBillTab {...props} />
        )}

        {activeTab === "Knowledge Center" && (
          <KnowledgeCenterTab {...props} />
        )}

        {activeTab === "Extension Downloads" && (
          <div className="space-y-4 text-sm text-slate-300">
            <div>
              <h3 className="text-base font-semibold text-slate-100">Extension Downloads</h3>
              <p className="mt-1 text-slate-400">
                The downloadable Chrome extension bundle is shown in the main page sections below.
                Use the button to jump to it.
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="text-xs uppercase tracking-[0.14em] text-slate-400">Quick access</p>
              <p className="mt-2 text-slate-300">
                This tab keeps the extension feature visible in the tab strip, while the actual download and admin management panels remain in the page body.
              </p>
              <button
                type="button"
                className="mt-3 rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
                onClick={() => {
                  document.getElementById("extension-download-center")?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
              >
                Jump to extension downloads
              </button>
            </div>
          </div>
        )}

        {activeTab === "Workflow Builder" && (
          <WorkflowBuilderTab {...props} />
        )}

        {activeTab === "Audit Trail" && (
          <AuditTrailTab {...props} />
        )}

        {activeTab === "Settings" && (
          <SettingsTab {...props} />
        )}
      </div>
    </section>
  );
}

// ΓöÇΓöÇ Teach Bill tab ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

function TeachBillTab(props: AdvancedToolsTabsProps) {
  const {
    learningPath, setLearningPath, learningWorkflowName, setLearningWorkflowName,
    learningGoal, setLearningGoal, learningSourceText, setLearningSourceText,
    learningBusyKey, learningFeedback, workflowDrafts, expandedDraftId, setExpandedDraftId,
    onCreateDraft, onDeleteDraft, onUpdateDraftStatus, onStartTeachingSession,
    onTestDraft, onPublishDraft, teachingSessionDraftId, draftsError,
    teachingTargetWorkerUuid, setTeachingTargetWorkerUuid, machines,
  } = props;

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold text-slate-100">Teach Bill a Workflow</h3>
        <p className="text-xs text-slate-400">Training experience: teach Bill like a human operator, test step-by-step, then publish.</p>
      </div>

      <div className="rounded-xl border border-cyan-400/20 bg-cyan-500/5 p-3 text-xs text-cyan-100">
        <p className="font-semibold">Training Stages</p>
        <p className="mt-1 text-slate-300">1) Setup ┬╖ 2) Teaching Mode ┬╖ 3) Step Builder ┬╖ 4) Validation ┬╖ 5) Test Mode ┬╖ 6) Publish</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-xs text-slate-400">
          Teaching path
          <select value={learningPath} onChange={(e) => setLearningPath(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-amber-400/60">
            <option value="plain_english">Describe workflow</option>
            <option value="demonstration">Demonstration / observed run</option>
            <option value="sop_checklist">Import SOP / checklist</option>
          </select>
        </label>
        <label className="text-xs text-slate-400">
          Workflow name
          <input type="text" value={learningWorkflowName} onChange={(e) => setLearningWorkflowName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-amber-400/60" />
        </label>
      </div>

      <label className="block text-xs text-slate-400">
        Worker (which computer opens the browser)
        <select value={teachingTargetWorkerUuid} onChange={(e) => setTeachingTargetWorkerUuid(e.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-amber-400/60">
          <option value="">ΓÇö Opens browser on this computer ΓÇö</option>
          {machines.filter((m) => m.online).map((m) => (
            <option key={m.machine_uuid} value={m.machine_uuid}>
              {m.machine_name} {m.status === "busy" ? "(busy)" : "(idle)"}
            </option>
          ))}
        </select>
      </label>

      <label className="block text-xs text-slate-400">
        Goal
        <input type="text" value={learningGoal} onChange={(e) => setLearningGoal(e.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-amber-400/60" />
      </label>

      <label className="block text-xs text-slate-400">
        Teaching notes
        <textarea rows={5} value={learningSourceText} onChange={(e) => setLearningSourceText(e.target.value)}
          placeholder={learningPath === "demonstration" ? "Optional notes. Start Teaching will open an empty draft." : "Describe steps line-by-line or paste checklist."}
          className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-amber-400/60" />
      </label>

      <div className="flex gap-2">
        <button type="button" onClick={onCreateDraft}
          disabled={learningBusyKey !== null || !learningWorkflowName.trim() || (learningPath !== "demonstration" && !learningSourceText.trim())}
          className={BTN_PRIMARY}>
          {learningBusyKey === "create-draft" ? "Starting..." : "Start Teaching Mode"}
        </button>
      </div>

      {draftsError && <p className="text-sm text-rose-300">{draftsError}</p>}
      {learningFeedback && (
        <div className={`rounded-lg px-3 py-2 text-sm ${learningFeedback.kind === "success" ? "border border-emerald-400/30 bg-emerald-500/10 text-emerald-200" : "border border-rose-400/30 bg-rose-500/10 text-rose-200"}`}>
          {learningFeedback.message} ┬╖ {learningFeedback.timestamp}
        </div>
      )}

      {/* Draft list */}
      {workflowDrafts.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-medium text-slate-400">Workflow Drafts ({workflowDrafts.length})</p>
          {workflowDrafts.map((draft) => (
            <article key={draft.draft_id} className={`rounded-xl border p-3 ${teachingSessionDraftId === draft.draft_id ? "border-amber-500/40 bg-amber-950/20" : "border-slate-800 bg-slate-950/70"}`}>
              <p className="text-sm font-semibold text-slate-100">{draft.workflow_name}</p>
              <p className="mt-1 text-xs text-slate-400">
                Path: {draft.learning_path} ┬╖ Status: {draft.review_status} ┬╖ Updated: {toDisplayTime(draft.updated_at)}
              </p>
              <p className="mt-1 text-xs text-slate-300">{draft.goal}</p>
                            {(draft.created_by_name || draft.last_updated_by_name || draft.approved_by_name) && (
                              <p className="mt-1 text-xs text-slate-500">
                                {draft.created_by_name && <>Taught by: {draft.created_by_name}</>}
                                {draft.last_updated_by_name && <> · Updated by: {draft.last_updated_by_name}</>}
                                {draft.approved_by_name && <> · Approved by: {draft.approved_by_name}</>}
                              </p>
                            )}
              <p className="mt-1 text-xs text-slate-500">Steps: {(draft.steps as unknown[]).length}</p>
              <p className="mt-1 text-xs text-slate-400">
                Readiness: {draft.execution_readiness?.runnable
                  ? "Runnable"
                  : (draft.execution_readiness?.manual_action_count || 0) > 0 && !(draft.execution_readiness?.has_start_url)
                    ? "Needs more teaching (manual-only / missing start URL)"
                    : "Needs more teaching"}
              </p>
              {draft.execution_readiness?.blocking_reasons?.length ? (
                <p className="mt-1 text-xs text-amber-300">
                  {draft.execution_readiness.blocking_reasons[0]}
                </p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={() => onDeleteDraft(draft.draft_id, draft.workflow_name)} disabled={learningBusyKey !== null} className={BTN_DANGER}>Delete</button>
                <button type="button" onClick={() => onUpdateDraftStatus(draft.draft_id, "in_review")} disabled={learningBusyKey !== null} className={BTN_SECONDARY}>In Review</button>
                <button type="button" onClick={() => onUpdateDraftStatus(draft.draft_id, "approved")} disabled={learningBusyKey !== null} className={BTN_SECONDARY}>Approve</button>
                <button type="button" onClick={() => onStartTeachingSession(draft.draft_id)} disabled={learningBusyKey !== null}
                  className={teachingSessionDraftId === draft.draft_id ? "rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-200 hover:bg-amber-500/20" : BTN_GHOST}>
                  {teachingSessionDraftId === draft.draft_id ? "ΓùÅ Teaching Active" : "Teach Steps"}
                </button>
                <button type="button" onClick={() => onTestDraft(draft.draft_id)} disabled={learningBusyKey !== null} className={BTN_GHOST}>
                  {learningBusyKey === `test-${draft.draft_id}` ? "Testing..." : "Test Mode"}
                </button>
                <button type="button" onClick={() => onPublishDraft(draft.draft_id)} disabled={learningBusyKey !== null || draft.review_status !== "approved"} className={BTN_PRIMARY}>
                  {learningBusyKey === `publish-${draft.draft_id}` ? "Publishing..." : "Publish"}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

// ΓöÇΓöÇ Workflow Builder tab ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

function WorkflowBuilderTab(props: AdvancedToolsTabsProps) {
  const {
    workflows, helperWorkflow, setHelperWorkflow, helperWorkerUuid, setHelperWorkerUuid,
    helperClientName, setHelperClientName, helperHouseholdName, setHelperHouseholdName,
    helperMaxClients, setHelperMaxClients, helperMaxPages, setHelperMaxPages,
    helperRetryFailedOnly, setHelperRetryFailedOnly, helperFreeText, setHelperFreeText,
    helperBusy, helperFeedback, onRunGuidedCommand, onRunFreeTextCommand,
    workflowsError, machines, loading, tasks, taskActionBusyKey, taskActionFeedback,
    onCancelTask, onRetryTask, selectedTask, setSelectedTask, actionError, response,
    onCreateTestTask, onCreateScreenshotTask, onCreateVisibleWorkflowTask,
    onRunSmartSherpa, onRunWorkflow, selectedWorkflowRunnable, selectedWorkflowBlockingReason,
    targetMachineUuid, setTargetMachineUuid,
  } = props;

  const activeTaskStatuses = new Set(["queued", "assigned", "running"]);

  const taskStatusLabel = (s?: string) => {
    const n = (s ?? "").toLowerCase();
    if (n === "running") return "In progress";
    if (n === "assigned") return "Assigned";
    if (n === "queued") return "Queued";
    if (n === "completed") return "Completed";
    if (n === "failed") return "Failed";
    return s ?? "Unknown";
  };

  const taskStatusCls = (s?: string) => {
    const n = (s ?? "").toLowerCase();
    if (n === "completed") return "bg-emerald-500/15 text-emerald-200 border border-emerald-400/30";
    if (n === "failed") return "bg-rose-500/15 text-rose-200 border border-rose-400/30";
    if (n === "running") return "bg-sky-500/15 text-sky-200 border border-sky-400/30";
    if (n === "queued" || n === "assigned") return "bg-amber-500/15 text-amber-200 border border-amber-400/30";
    return "bg-slate-700/60 text-slate-200";
  };

  const workerStatusText = (m: Machine) => {
    if (!m.online) return "Offline";
    const s = (m.status ?? "").toLowerCase();
    if (s === "idle") return "Online ┬╖ Idle";
    if (s === "busy" || s === "running") return "Online ┬╖ Busy";
    return "Online";
  };

  return (
    <div className="space-y-6">
      {/* Target worker selector */}
      <div>
        <label htmlFor="wf-target-machine" className="mb-1 block text-xs text-slate-400">Target Worker</label>
        <select id="wf-target-machine" value={targetMachineUuid} onChange={(e) => setTargetMachineUuid(e.target.value)}
          className="w-full max-w-sm rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-cyan-400/70">
          <option value="">Auto assign best available</option>
          {machines.map((m) => m.machine_uuid ? (
            <option key={m.machine_uuid} value={m.machine_uuid}>
              {m.machine_name ?? "unknown"} ┬╖ {workerStatusText(m)}
            </option>
          ) : null)}
        </select>
      </div>

      {/* Quick run buttons */}
      <div>
        <p className="mb-2 text-xs font-medium text-slate-400">Quick Run</p>
        {workflowsError && <p className="mb-2 text-xs text-rose-300">{workflowsError}</p>}
        {workflows.length > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <select value={helperWorkflow} onChange={(e) => setHelperWorkflow(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-cyan-400/70">
              {workflows.map((wf) => <option key={wf.workflow_name} value={wf.workflow_name}>{wf.workflow_name}</option>)}
            </select>
            <button
              type="button"
              onClick={() => onRunWorkflow(helperWorkflow)}
              disabled={loading || !helperWorkflow || !selectedWorkflowRunnable}
              title={!selectedWorkflowRunnable ? (selectedWorkflowBlockingReason ?? "This workflow needs more teaching before it can run.") : undefined}
              className={BTN_PRIMARY}
            >
              {loading ? "Starting..." : "Run Workflow"}
            </button>
          </div>
        )}
        {!selectedWorkflowRunnable && selectedWorkflowBlockingReason ? (
          <p className="mb-2 text-xs text-amber-300">Run blocked: {selectedWorkflowBlockingReason}</p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={onCreateTestTask} disabled={loading} className={BTN_SECONDARY}>{loading ? "Creating..." : "Create Test Task"}</button>
          <button type="button" onClick={onCreateScreenshotTask} disabled={loading} className={BTN_SECONDARY}>Screenshot Task</button>
          <button type="button" onClick={onCreateVisibleWorkflowTask} disabled={loading} className={BTN_SECONDARY}>Visible Workflow</button>
          <button type="button" onClick={onRunSmartSherpa} disabled={loading} className={BTN_PRIMARY}>Run Smart Sherpa Sync</button>
        </div>
      </div>

      {/* Guided command builder */}
      <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
        <p className="mb-3 text-xs font-medium text-slate-400">Guided Command Builder</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-slate-400">Workflow
            <select value={helperWorkflow} onChange={(e) => setHelperWorkflow(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-cyan-400/70">
              {workflows.map((wf) => <option key={wf.workflow_name} value={wf.workflow_name}>{wf.workflow_name}</option>)}
            </select>
          </label>
          <label className="text-xs text-slate-400">Worker override
            <select value={helperWorkerUuid} onChange={(e) => setHelperWorkerUuid(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-cyan-400/70">
              <option value="">Use selected / auto</option>
              {machines.filter((m) => m.machine_uuid).map((m) => (
                <option key={m.machine_uuid} value={m.machine_uuid}>{m.machine_name ?? "unknown"} ┬╖ {workerStatusText(m)}</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-400">Client name
            <input type="text" value={helperClientName} onChange={(e) => setHelperClientName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-cyan-400/70" />
          </label>
          <label className="text-xs text-slate-400">Household name
            <input type="text" value={helperHouseholdName} onChange={(e) => setHelperHouseholdName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-cyan-400/70" />
          </label>
          <label className="text-xs text-slate-400">Max clients
            <input type="number" min={1} value={helperMaxClients} onChange={(e) => setHelperMaxClients(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-cyan-400/70" />
          </label>
          <label className="text-xs text-slate-400">Max pages
            <input type="number" min={1} value={helperMaxPages} onChange={(e) => setHelperMaxPages(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-cyan-400/70" />
          </label>
        </div>
        <label className="mt-3 flex items-center gap-2 text-xs text-slate-300">
          <input type="checkbox" checked={helperRetryFailedOnly} onChange={(e) => setHelperRetryFailedOnly(e.target.checked)} className="h-4 w-4 rounded border-slate-600 bg-slate-900 accent-cyan-400" />
          Retry failed items only
        </label>
        <button type="button" onClick={onRunGuidedCommand} disabled={helperBusy || !helperWorkflow} className={`mt-3 ${BTN_PRIMARY}`}>
          {helperBusy ? "Submitting..." : "Run Guided Command"}
        </button>

        <div className="mt-4 border-t border-slate-800 pt-4">
          <label className="text-xs text-slate-400">Free-text fallback
            <textarea rows={2} value={helperFreeText} onChange={(e) => setHelperFreeText(e.target.value)}
              placeholder="run marketplace workflow on worker A max clients 25"
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-cyan-400/70" />
          </label>
          <button type="button" onClick={onRunFreeTextCommand} disabled={helperBusy || !helperFreeText.trim()} className={BTN_SECONDARY}>
            Submit Free-text Command
          </button>
        </div>
        {helperFeedback && (
          <div className={`mt-3 rounded-lg px-3 py-2 text-sm ${helperFeedback.kind === "success" ? "border border-emerald-400/30 bg-emerald-500/10 text-emerald-200" : "border border-rose-400/30 bg-rose-500/10 text-rose-200"}`}>
            {helperFeedback.message} ┬╖ {helperFeedback.timestamp}
          </div>
        )}
      </div>

      {/* All tasks */}
      <div>
        <p className="mb-2 text-xs font-medium text-slate-400">All Tasks</p>
        {taskActionFeedback && (
          <div className={`mb-3 rounded-lg px-3 py-2 text-sm ${taskActionFeedback.kind === "success" ? "border border-emerald-400/30 bg-emerald-500/10 text-emerald-200" : "border border-rose-400/30 bg-rose-500/10 text-rose-200"}`}>
            {taskActionFeedback.message} ┬╖ {taskActionFeedback.timestamp}
          </div>
        )}
        {actionError && (
          <div className="mb-3 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{actionError}</div>
        )}
        {tasks.length === 0 ? (
          <p className="text-sm text-slate-400">No tasks yet.</p>
        ) : (
          <div className="max-h-[480px] space-y-2 overflow-auto pr-1">
            {tasks.map((task, idx) => {
              const status = (task.status ?? "").toLowerCase();
              const canCancel = !!task.id && activeTaskStatuses.has(status);
              const canRetry = !!task.id && status === "failed";
              const isSelected = selectedTask?.id === task.id;
              return (
                <div key={task.id ?? `task-${idx}`} className={`rounded-xl border p-3 ${isSelected ? "border-cyan-400/50 bg-slate-900/90" : "border-slate-800 bg-slate-900/60"}`}>
                  <button type="button" onClick={() => setSelectedTask(task)} className="w-full text-left">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold">{task.payload?.task_type ?? "General Task"}</p>
                      <span className={`rounded-full px-2.5 py-1 text-xs ${taskStatusCls(task.status)}`}>{taskStatusLabel(task.status)}</span>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">{shortTaskId(task.id)} ┬╖ {toDisplayTime(task.created_at)}</p>
                    {task.error && <p className="mt-1 text-xs text-rose-300">{task.error}</p>}
                  </button>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button type="button" disabled={!canCancel || taskActionBusyKey !== null} onClick={() => onCancelTask(task.id)} className={BTN_DANGER}>
                      {taskActionBusyKey === `cancel-${task.id}` ? "Canceling..." : "Cancel"}
                    </button>
                    <button type="button" disabled={!canRetry || taskActionBusyKey !== null} onClick={() => onRetryTask(task)} className={BTN_GHOST}>
                      {taskActionBusyKey === `retry-${task.id}` ? "Retrying..." : "Retry"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {response !== null && response !== undefined && (
          <details className="mt-3 rounded-xl border border-slate-800 bg-slate-950/70 p-3">
            <summary className="cursor-pointer text-xs font-medium text-slate-400">Last API response</summary>
            <pre className="mt-2 overflow-auto text-[11px] text-slate-300">{JSON.stringify(response, null, 2)}</pre>
          </details>
        )}
      </div>
    </div>
  );
}

function KnowledgeCenterTab(props: AdvancedToolsTabsProps) {
  const {
    currentUserRole,
    knowledgeEntries,
    knowledgeLoading,
    knowledgeError,
    knowledgeActionBusyKey,
    knowledgeActionFeedback,
    onRefreshKnowledge,
    onCreateKnowledge,
    onUpdateKnowledge,
    onArchiveKnowledge,
    onActivateKnowledge,
  } = props;

  const isAdmin = currentUserRole === "admin";
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "draft" | "archived">("all");
  const [tagFilter, setTagFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [newAppliesTo, setNewAppliesTo] = useState("");
  const [newTags, setNewTags] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newStatus, setNewStatus] = useState<"active" | "draft" | "archived">("draft");
  const [newSourceType, setNewSourceType] = useState<"manual" | "document" | "imported" | "system">("manual");

  const selectedEntry = knowledgeEntries.find((entry) => entry.knowledge_id === selectedId) ?? null;

  const [editTitle, setEditTitle] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [editAppliesTo, setEditAppliesTo] = useState("");
  const [editTags, setEditTags] = useState("");
  const [editContent, setEditContent] = useState("");
  const [editStatus, setEditStatus] = useState<"active" | "draft" | "archived">("draft");
  const [editSourceType, setEditSourceType] = useState<"manual" | "document" | "imported" | "system">("manual");

  const filteredEntries = knowledgeEntries.filter((entry) => {
    if (statusFilter !== "all" && entry.status !== statusFilter) return false;
    if (categoryFilter.trim() && !entry.category.toLowerCase().includes(categoryFilter.trim().toLowerCase())) return false;
    if (tagFilter.trim()) {
      const needle = tagFilter.trim().toLowerCase();
      if (!entry.tags.some((tag) => tag.toLowerCase().includes(needle))) return false;
    }
    if (search.trim()) {
      const needle = search.trim().toLowerCase();
      const blob = [entry.title, entry.category, entry.content, entry.tags.join(" "), entry.applies_to.join(" ")].join(" ").toLowerCase();
      if (!blob.includes(needle)) return false;
    }
    return true;
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-slate-100">Knowledge Center</h3>
          <p className="text-xs text-slate-400">Reference knowledge for standards, terminology, policies, and CRM guidance.</p>
        </div>
        <button type="button" onClick={onRefreshKnowledge} className={BTN_SECONDARY}>Refresh</button>
      </div>

      <div className="grid gap-2 sm:grid-cols-4">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search title/content"
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100"
        />
        <input
          value={categoryFilter}
          onChange={(event) => setCategoryFilter(event.target.value)}
          placeholder="Filter by category"
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100"
        />
        <input
          value={tagFilter}
          onChange={(event) => setTagFilter(event.target.value)}
          placeholder="Filter by tag"
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100"
        />
        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as "all" | "active" | "draft" | "archived")}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100"
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="draft">Draft</option>
          <option value="archived">Archived</option>
        </select>
      </div>

      {knowledgeError && <p className="text-sm text-rose-300">{knowledgeError}</p>}
      {knowledgeActionFeedback && (
        <div className={`rounded-lg px-3 py-2 text-sm ${knowledgeActionFeedback.kind === "success" ? "border border-emerald-400/30 bg-emerald-500/10 text-emerald-200" : "border border-rose-400/30 bg-rose-500/10 text-rose-200"}`}>
          {knowledgeActionFeedback.message} - {knowledgeActionFeedback.timestamp}
        </div>
      )}

      {isAdmin && (
        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
          <p className="mb-2 text-xs uppercase tracking-[0.14em] text-slate-400">Create Knowledge Entry</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} placeholder="Title" className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
            <input value={newCategory} onChange={(event) => setNewCategory(event.target.value)} placeholder="Category" className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
            <input value={newAppliesTo} onChange={(event) => setNewAppliesTo(event.target.value)} placeholder="Applies To (comma separated)" className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
            <input value={newTags} onChange={(event) => setNewTags(event.target.value)} placeholder="Tags (comma separated)" className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
            <select value={newSourceType} onChange={(event) => setNewSourceType(event.target.value as "manual" | "document" | "imported" | "system")} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100">
              <option value="manual">manual</option>
              <option value="document">document</option>
              <option value="imported">imported</option>
              <option value="system">system</option>
            </select>
            <select value={newStatus} onChange={(event) => setNewStatus(event.target.value as "active" | "draft" | "archived")} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100">
              <option value="draft">draft</option>
              <option value="active">active</option>
              <option value="archived">archived</option>
            </select>
          </div>
          <textarea
            rows={4}
            value={newContent}
            onChange={(event) => setNewContent(event.target.value)}
            placeholder="Knowledge content"
            className="mt-2 min-h-[240px] w-full resize-y rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          />
          <button
            type="button"
            className="mt-2 rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50"
            disabled={knowledgeActionBusyKey !== null || !newTitle.trim() || !newCategory.trim() || !newContent.trim()}
            onClick={() => {
              onCreateKnowledge({
                title: newTitle.trim(),
                category: newCategory.trim(),
                applies_to: newAppliesTo.split(",").map((item) => item.trim()).filter(Boolean),
                tags: newTags.split(",").map((item) => item.trim()).filter(Boolean),
                content: newContent.trim(),
                source_type: newSourceType,
                status: newStatus,
              });
              setNewTitle("");
              setNewCategory("");
              setNewAppliesTo("");
              setNewTags("");
              setNewContent("");
              setNewStatus("draft");
              setNewSourceType("manual");
            }}
          >
            {knowledgeActionBusyKey === "knowledge-create" ? "Creating..." : "Create Entry"}
          </button>
        </div>
      )}

      {knowledgeLoading ? (
        <p className="text-sm text-slate-400">Loading knowledge entries...</p>
      ) : filteredEntries.length === 0 ? (
        <p className="text-sm text-slate-400">No knowledge entries match your filters.</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
          <div className="max-h-[520px] space-y-2 overflow-auto pr-1">
            {filteredEntries.map((entry) => (
              <button
                key={entry.knowledge_id}
                type="button"
                onClick={() => {
                  setSelectedId(entry.knowledge_id);
                  setEditTitle(entry.title);
                  setEditCategory(entry.category);
                  setEditAppliesTo(entry.applies_to.join(", "));
                  setEditTags(entry.tags.join(", "));
                  setEditContent(entry.content);
                  setEditStatus(entry.status);
                  setEditSourceType(entry.source_type);
                }}
                className={`w-full rounded-xl border p-3 text-left ${selectedId === entry.knowledge_id ? "border-cyan-400/50 bg-slate-900/85" : "border-slate-800 bg-slate-950/70"}`}
              >
                <p className="text-sm font-semibold text-slate-100">{entry.title}</p>
                <p className="mt-1 text-xs text-slate-400">{entry.category} - {entry.status} - v{entry.version}</p>
                <p className="mt-1 text-xs text-slate-500">Tags: {entry.tags.join(", ") || "none"}</p>
                <p className="mt-1 text-xs text-slate-500">Updated: {toDisplayTime(entry.updated_at)} - By: {entry.created_by_name || "unknown"}</p>
              </button>
            ))}
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
            {!selectedEntry ? (
              <p className="text-sm text-slate-400">Select an entry to preview and edit.</p>
            ) : (
              <div className="space-y-2">
                {isAdmin ? (
                  <>
                    <input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
                    <input value={editCategory} onChange={(event) => setEditCategory(event.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
                    <input value={editAppliesTo} onChange={(event) => setEditAppliesTo(event.target.value)} placeholder="Applies To (comma separated)" className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
                    <input value={editTags} onChange={(event) => setEditTags(event.target.value)} placeholder="Tags (comma separated)" className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
                    <div className="grid gap-2 sm:grid-cols-2">
                      <select value={editSourceType} onChange={(event) => setEditSourceType(event.target.value as "manual" | "document" | "imported" | "system")} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100">
                        <option value="manual">manual</option>
                        <option value="document">document</option>
                        <option value="imported">imported</option>
                        <option value="system">system</option>
                      </select>
                      <select value={editStatus} onChange={(event) => setEditStatus(event.target.value as "active" | "draft" | "archived")} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100">
                        <option value="draft">draft</option>
                        <option value="active">active</option>
                        <option value="archived">archived</option>
                      </select>
                    </div>
                    <textarea rows={10} value={editContent} onChange={(event) => setEditContent(event.target.value)} className="min-h-[320px] w-full resize-y rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className={BTN_PRIMARY}
                        disabled={knowledgeActionBusyKey !== null}
                        onClick={() => onUpdateKnowledge(selectedEntry.knowledge_id, {
                          title: editTitle.trim(),
                          category: editCategory.trim(),
                          applies_to: editAppliesTo.split(",").map((item) => item.trim()).filter(Boolean),
                          tags: editTags.split(",").map((item) => item.trim()).filter(Boolean),
                          content: editContent,
                          status: editStatus,
                          source_type: editSourceType,
                        })}
                      >
                        {knowledgeActionBusyKey === `knowledge-update-${selectedEntry.knowledge_id}` ? "Saving..." : "Save"}
                      </button>
                      <button type="button" className={BTN_GHOST} disabled={knowledgeActionBusyKey !== null} onClick={() => onActivateKnowledge(selectedEntry.knowledge_id)}>
                        Activate
                      </button>
                      <button type="button" className={BTN_DANGER} disabled={knowledgeActionBusyKey !== null} onClick={() => onArchiveKnowledge(selectedEntry.knowledge_id)}>
                        Archive
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-lg font-semibold text-slate-100">{selectedEntry.title}</p>
                    <p className="text-xs text-slate-400">{selectedEntry.category} - {selectedEntry.status}</p>
                    <p className="text-xs text-slate-500">Tags: {selectedEntry.tags.join(", ") || "none"}</p>
                    <p className="text-xs text-slate-500">Applies To: {selectedEntry.applies_to.join(", ") || "none"}</p>
                    <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-200">{selectedEntry.content}</pre>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ΓöÇΓöÇ Audit Trail tab ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

function AuditTrailTab({ auditEntries, onRefreshAudit, auditError, chatHistory }: AdvancedToolsTabsProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-slate-100">Audit Trail</h3>
          <p className="text-xs text-slate-400">Recent command history and outcomes.</p>
        </div>
        <button type="button" onClick={onRefreshAudit} className={BTN_SECONDARY}>Refresh</button>
      </div>

      {/* Chat history */}
      {chatHistory.length > 1 && (
        <details className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <summary className="cursor-pointer text-xs font-medium text-slate-300">Command Session History ({chatHistory.length - 1} messages)</summary>
          <div className="mt-3 max-h-[320px] space-y-2 overflow-auto pr-1">
            {chatHistory.slice(1).map((entry, idx) => (
              <div key={`chat-${idx}`} className={entry.role === "user" ? "ml-6 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-2" : "mr-6 rounded-xl border border-slate-800 bg-slate-900/80 p-2"}>
                <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">{entry.role === "user" ? "You" : "Bill"}</p>
                <p className="whitespace-pre-wrap text-xs text-slate-200">{entry.message}</p>
              </div>
            ))}
          </div>
        </details>
      )}

      {auditError ? (
        <p className="text-sm text-rose-300">{auditError}</p>
      ) : auditEntries.length === 0 ? (
        <p className="text-sm text-slate-400">No command history yet.</p>
      ) : (
        <div className="max-h-[520px] space-y-2 overflow-auto pr-1">
          {auditEntries.map((entry, idx) => (
            <article key={`audit-${idx}`} className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <p className="text-xs text-slate-500">{toDisplayTime(entry.timestamp)}</p>
              <p className="mt-1 text-sm text-slate-200">{entry.original_user_text ?? "-"}</p>
              <p className="mt-1.5 text-xs text-slate-400">
                Intent: <span className="text-slate-300">{entry.interpreted_intent ?? "-"}</span>
                {" ┬╖ "}Workflow: <span className="text-slate-300">{entry.selected_workflow ?? "-"}</span>
                {" ┬╖ "}Worker: <span className="text-slate-300">{entry.selected_worker ?? "-"}</span>
              </p>
              <p className="mt-1 text-sm text-slate-300">{entry.after_execution ?? "No outcome recorded."}</p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

// ΓöÇΓöÇ Settings tab ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

function SettingsTab(props: AdvancedToolsTabsProps) {
  const {
    workerReleases, workerDeployStatus,
    releaseUploadVersion, setReleaseUploadVersion,
    releaseUploadNotes, setReleaseUploadNotes,
    releaseUploadChannel, setReleaseUploadChannel,
    releaseUploadFile, setReleaseUploadFile,
    releaseUploadBusy, releaseBusyKey, releasesFeedback,
    deployBusy, deployForce, setDeployForce, deployIdleOnly, setDeployIdleOnly,
    onUploadRelease, onActivateRelease, onDeleteRelease, onDeployToWorkers,
    onRefreshBrainPanels,
  } = props;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-slate-100">Worker Updates</h3>
          <p className="text-xs text-slate-400">
            Manage releases and push updates to worker machines.
            {workerDeployStatus?.active_release_version && (
              <span className="ml-2 text-cyan-400">Active: v{workerDeployStatus.active_release_version}</span>
            )}
          </p>
        </div>
        <button type="button" onClick={onRefreshBrainPanels} className={BTN_SECONDARY}>Refresh</button>
      </div>

      {releasesFeedback && (
        <div className={`rounded-lg px-3 py-2 text-xs ${releasesFeedback.kind === "success" ? "bg-emerald-500/10 text-emerald-300" : "bg-rose-500/10 text-rose-300"}`}>
          {releasesFeedback.message}
        </div>
      )}

      {/* Worker update status */}
      {workerDeployStatus && workerDeployStatus.workers.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium text-slate-400">Worker Status</p>
          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-left text-slate-500">
                  <th className="px-3 py-2 font-medium">Worker</th>
                  <th className="px-3 py-2 font-medium">Version</th>
                  <th className="px-3 py-2 font-medium">Update Status</th>
                  <th className="px-3 py-2 font-medium">Target</th>
                  <th className="px-3 py-2 font-medium" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {workerDeployStatus.workers.map((w) => (
                  <tr key={w.machine_uuid} className="text-slate-300">
                    <td className="px-3 py-2 font-medium">{w.machine_name ?? shortTaskId(w.machine_uuid)}</td>
                    <td className="px-3 py-2 font-mono">{w.worker_version ?? "-"}</td>
                    <td className="px-3 py-2">
                      {w.update_status ? (
                        <span className={`rounded-full px-2 py-0.5 ${updateStatusClasses(w.update_status)}`}>{w.update_status}</span>
                      ) : <span className="text-slate-600">ΓÇö</span>}
                      {w.update_error && <p className="mt-0.5 truncate text-[10px] text-rose-400">{w.update_error}</p>}
                    </td>
                    <td className="px-3 py-2 font-mono text-slate-500">{w.update_target_version ?? "ΓÇö"}</td>
                    <td className="px-3 py-2">
                      <button type="button" onClick={() => onDeployToWorkers([w.machine_uuid])} disabled={deployBusy || !workerDeployStatus.active_release_version} className={BTN_GHOST}>Deploy</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button type="button" onClick={() => onDeployToWorkers()} disabled={deployBusy || !workerDeployStatus.active_release_version} className={BTN_PRIMARY}>
              {deployBusy ? "DeployingΓÇª" : "Deploy to All Workers"}
            </button>
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400">
              <input type="checkbox" checked={deployForce} onChange={(e) => setDeployForce(e.target.checked)} className="accent-cyan-400" />
              Force (re-deploy even if up to date)
            </label>
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400">
              <input type="checkbox" checked={deployIdleOnly} onChange={(e) => setDeployIdleOnly(e.target.checked)} className="accent-cyan-400" />
              Idle workers only
            </label>
          </div>
        </div>
      )}

      {/* Releases */}
      {workerReleases.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium text-slate-400">Available Releases</p>
          <div className="space-y-2">
            {workerReleases.map((release) => (
              <div key={release.id} className={`rounded-xl border p-3 ${release.is_active ? "border-cyan-400/40 bg-cyan-500/5" : "border-slate-800 bg-slate-900/60"}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-semibold text-slate-100">v{release.version}</span>
                      {release.is_active && <span className="rounded-full bg-cyan-500/20 px-2 py-0.5 text-[10px] text-cyan-300 border border-cyan-400/30">Active</span>}
                      <span className="rounded-full bg-slate-700/60 px-2 py-0.5 text-[10px] text-slate-400 border border-slate-600/40">{release.channel}</span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-slate-500">{toDisplayTime(release.upload_time)}</p>
                    {release.release_notes && <p className="mt-1 text-xs text-slate-400">{release.release_notes}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    {!release.is_active && (
                      <button type="button" onClick={() => onActivateRelease(release.id)} disabled={releaseBusyKey !== null} className={BTN_GHOST}>
                        {releaseBusyKey === `activate-${release.id}` ? "ΓÇª" : "Activate"}
                      </button>
                    )}
                    <button type="button" onClick={() => onDeleteRelease(release.id)} disabled={releaseBusyKey !== null} className={BTN_DANGER}>
                      {releaseBusyKey === `delete-${release.id}` ? "ΓÇª" : "Delete"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upload new release */}
      <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
        <p className="mb-3 text-xs font-medium text-slate-400">Publish New Release</p>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11px] text-slate-500">Version</label>
              <input type="text" placeholder="0.3.22" value={releaseUploadVersion} onChange={(e) => setReleaseUploadVersion(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-100 placeholder-slate-600 focus:border-cyan-400/60 focus:outline-none" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-slate-500">Channel</label>
              <select value={releaseUploadChannel} onChange={(e) => setReleaseUploadChannel(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-100 focus:border-cyan-400/60 focus:outline-none">
                <option value="optional">optional</option>
                <option value="required">required</option>
              </select>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-slate-500">Release Notes</label>
            <textarea rows={2} placeholder="What changed in this releaseΓÇª" value={releaseUploadNotes} onChange={(e) => setReleaseUploadNotes(e.target.value)}
              className="w-full resize-none rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-100 placeholder-slate-600 focus:border-cyan-400/60 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-slate-500">Package (.zip)</label>
            <input type="file" accept=".zip" onChange={(e) => setReleaseUploadFile(e.target.files?.[0] ?? null)}
              className="w-full text-xs text-slate-400 file:mr-3 file:rounded file:border-0 file:bg-slate-700 file:px-2.5 file:py-1 file:text-xs file:text-slate-200 file:cursor-pointer" />
          </div>
          <button type="button" onClick={onUploadRelease} disabled={releaseUploadBusy || !releaseUploadVersion.trim() || !releaseUploadFile} className={BTN_PRIMARY}>
            {releaseUploadBusy ? "UploadingΓÇª" : "Publish Release"}
          </button>
        </div>
      </div>
    </div>
  );
}
