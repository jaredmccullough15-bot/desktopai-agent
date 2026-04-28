"use client";

import { type Dispatch, type SetStateAction } from "react";
import type { useBillVoice } from "../hooks/useBillVoice";
import type { useBillMic } from "../hooks/useBillMic";

type BillVoiceHandle = ReturnType<typeof useBillVoice>;
type BillMicHandle = ReturnType<typeof useBillMic>;

interface WorkflowRecord {
  workflow_name: string;
  description: string;
}

interface CommandCenterCardProps {
  chatInput: string;
  setChatInput: Dispatch<SetStateAction<string>>;
  chatLoading: boolean;
  onSubmit: () => void;
  commandVoiceEnabled: boolean;
  setCommandVoiceEnabled: Dispatch<SetStateAction<boolean>>;
  voiceSupported: boolean;
  isListening: boolean;
  startListening: () => void;
  stopListening: () => void;
  billVoice: BillVoiceHandle;
  commandMic: BillMicHandle;
  workflows: WorkflowRecord[];
  loading: boolean;
  helperWorkflow: string;
  setHelperWorkflow: Dispatch<SetStateAction<string>>;
  onRunWorkflow: (name: string) => void;
  onQuickAction: (command: string) => void;
}

const QUICK_ACTIONS = [
  { label: "Run Marketplace Workflow", command: "run marketplace workflow" },
  { label: "Check Worker Status", command: "which worker is free?" },
  { label: "Show Active Tasks", command: "show active tasks" },
  { label: "Retry Failed Tasks", command: "retry last failed task" },
  { label: "Get Summary", command: "summarize all workers" },
];

export function CommandCenterCard({
  chatInput,
  setChatInput,
  chatLoading,
  onSubmit,
  commandVoiceEnabled,
  setCommandVoiceEnabled,
  voiceSupported,
  isListening,
  startListening,
  stopListening,
  billVoice,
  commandMic,
  loading,
  onQuickAction,
}: CommandCenterCardProps) {
  return (
    <section className="rounded-2xl border border-cyan-500/25 bg-slate-900/80 p-5 shadow-[0_24px_45px_-30px_rgba(8,145,178,0.7)]">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-slate-50">Command Center</h2>
        <p className="text-xs text-slate-400">Tell Bill what to do. Natural language control for workflows and tasks.</p>
      </div>

      {/* Textarea + mic */}
      <div className="relative rounded-xl border border-slate-700/80 bg-slate-950/70 p-1 shadow-inner">
        <textarea
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
          rows={5}
          placeholder="Tell Bill what you want to accomplish..."
          className="w-full resize-none rounded-lg border-0 bg-transparent px-4 py-3 pr-12 text-sm leading-relaxed text-slate-100 outline-none placeholder:text-slate-600"
        />
        {/* Mic icon overlay */}
        {voiceSupported && (
          <button
            type="button"
            onClick={isListening ? stopListening : startListening}
            title={isListening ? "Stop listening" : "Speak command"}
            className={`absolute right-3 top-3 rounded-lg p-1.5 transition ${
              isListening
                ? "animate-pulse bg-rose-500/80 text-white"
                : "text-slate-500 hover:text-cyan-300"
            }`}
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
          </button>
        )}
      </div>

      {/* Controls row */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {/* Voice On toggle */}
        <button
          type="button"
          onClick={() => setCommandVoiceEnabled((v) => !v)}
          className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
            commandVoiceEnabled
              ? "border-cyan-400/40 bg-cyan-500/15 text-cyan-300"
              : "border-slate-700 bg-slate-900 text-slate-500 hover:text-slate-300"
          }`}
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.536 8.464a5 5 0 010 7.072M12 6v12M8.464 8.464a5 5 0 000 7.072" />
          </svg>
          {commandVoiceEnabled ? "Voice On" : "Voice Off"}
          <svg className="h-3 w-3 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {/* Stop voice */}
        {commandVoiceEnabled && (
          <button
            type="button"
            onClick={() => billVoice.stopPlayback()}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-400 transition hover:text-slate-200"
          >
            Stop Voice
          </button>
        )}

        {/* Experimental mic capture */}
        <button
          type="button"
          disabled={!commandMic.supported}
          onClick={() => {
            if (commandMic.isRecording) {
              commandMic.stopRecording();
            } else {
              void commandMic.requestPermission().then((granted) => {
                if (granted) void commandMic.startRecording();
              });
            }
          }}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-400 transition hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {commandMic.isRecording ? "Stop Mic" : "🎙 Mic"}
        </button>

        <div className="flex-1" />

        {/* Send Command */}
        <button
          type="button"
          onClick={onSubmit}
          disabled={chatLoading || loading || !chatInput.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-cyan-500 px-5 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {chatLoading ? "Thinking..." : "Send Command"}
          {!chatLoading && (
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M22 2L11 13M22 2L15 22l-4-9-9-4 19-7z" />
            </svg>
          )}
        </button>
      </div>

      {/* Voice status line */}
      {(billVoice.lastError || !billVoice.config?.configured) && (
        <p className="mt-1.5 text-[11px] text-slate-500">
          ElevenLabs: {billVoice.config?.configured ? "ready" : "unavailable"}
          {billVoice.lastError && <span className="ml-2 text-rose-400">· {billVoice.lastError}</span>}
        </p>
      )}

      {/* Quick Actions */}
      <div className="mt-4 border-t border-slate-800/70 pt-4">
        <p className="mb-2 text-xs font-medium text-slate-500">Quick Actions</p>
        <div className="flex flex-wrap gap-2">
          {QUICK_ACTIONS.map((action) => (
            <button
              key={action.command}
              type="button"
              onClick={() => onQuickAction(action.command)}
              disabled={chatLoading || loading}
              className="flex items-center gap-1.5 rounded-lg border border-slate-700/80 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 transition hover:border-cyan-400/50 hover:bg-cyan-500/10 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {action.label}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
