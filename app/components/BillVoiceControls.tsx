"use client";

import { useMemo, useState } from "react";

import { useBillMic } from "../hooks/useBillMic";
import type { UseBillVoiceReturn } from "../hooks/useBillVoice";

type Props = {
  voice: UseBillVoiceReturn;
};

const DEFAULT_PREVIEW_TEXT = "Bill voice check. Recovery systems are active and ready.";

export default function BillVoiceControls({ voice }: Props) {
  const [text, setText] = useState(DEFAULT_PREVIEW_TEXT);
  const [emotion, setEmotion] = useState<string>("neutral");
  const [styleProfile, setStyleProfile] = useState<string>("default");
  const mic = useBillMic();

  const voiceReady = !!voice.config?.voice_enabled && !!voice.config?.configured;

  const supportedEmotions = useMemo(
    () => voice.config?.supported_emotions ?? ["neutral", "helpful", "empathetic", "alert", "confident"],
    [voice.config?.supported_emotions],
  );

  const supportedStyles = useMemo(
    () => voice.config?.supported_style_profiles ?? ["default", "calm", "energetic", "urgent", "empathetic"],
    [voice.config?.supported_style_profiles],
  );

  return (
    <section className="rounded-2xl border border-cyan-500/25 bg-slate-900/75 p-5 shadow-[0_24px_45px_-30px_rgba(8,145,178,0.7)]">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-cyan-100">Bill Voice Controls</h2>
          <p className="text-xs text-slate-400">ElevenLabs playback via Bill Core backend proxy.</p>
        </div>
        <span
          className={`rounded-full border px-2.5 py-1 text-xs ${
            voiceReady
              ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-200"
              : "border-amber-400/40 bg-amber-500/10 text-amber-200"
          }`}
        >
          {voiceReady ? "Voice Ready" : "Voice Unavailable"}
        </span>
      </div>

      <div className="space-y-3">
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={3}
          className="w-full resize-none rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-400/70 focus:ring-2 focus:ring-cyan-500/30"
          placeholder="Enter text for Bill to speak"
        />

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-slate-400">
            Emotion
            <select
              value={emotion}
              onChange={(event) => setEmotion(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            >
              {supportedEmotions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>

          <label className="text-xs text-slate-400">
            Style Profile
            <select
              value={styleProfile}
              onChange={(event) => setStyleProfile(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            >
              {supportedStyles.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void voice.speakText({ text, emotion, style_profile: styleProfile })}
            disabled={voice.loadingAudio || !text.trim()}
            className="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {voice.loadingAudio ? "Generating..." : "Play"}
          </button>

          <button
            type="button"
            onClick={voice.stopPlayback}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-cyan-400/60 hover:text-cyan-100"
          >
            Stop
          </button>

          <button
            type="button"
            onClick={() => void voice.previewStyle({ text, emotion, style_profile: styleProfile })}
            disabled={voice.loadingAudio || !text.trim()}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-cyan-400/60 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Preview Style
          </button>

          <button
            type="button"
            onClick={() => void voice.refreshConfig()}
            disabled={voice.loadingConfig}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-cyan-400/60 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {voice.loadingConfig ? "Refreshing..." : "Refresh Config"}
          </button>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-xs text-slate-300">
          <p className="font-semibold text-slate-200">Realtime Mic Scaffold</p>
          <p className="mt-1 text-slate-400">Microphone capture is scaffolded for a future speech-to-text handoff.</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void mic.requestPermission()}
              disabled={!mic.supported}
              className="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Request Mic Permission
            </button>
            <button
              type="button"
              disabled={!mic.supported || mic.isRecording}
              onClick={() => void mic.startRecording()}
              className="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Start Recording
            </button>
            <button
              type="button"
              disabled={!mic.supported || !mic.isRecording}
              onClick={() => {
                mic.stopRecording();
              }}
              className="rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Stop Recording
            </button>
            <span className="text-slate-500">
              {mic.supported
                ? `Permission: ${mic.permission} · ${mic.isRecording ? "recording" : "idle"}`
                : "Mic API not supported in this browser"}
            </span>
          </div>
        </div>

        {voice.lastMeta && (
          <p className="text-xs text-slate-400">
            Last voice: emotion={voice.lastMeta.emotion ?? "-"}, style={voice.lastMeta.style ?? "-"},
            format={voice.lastMeta.outputFormat ?? "-"}, duration={voice.lastMeta.durationMs ?? 0}ms,
            truncated={String(voice.lastMeta.truncated ?? false)}
          </p>
        )}

        {voice.config && !voice.config.configured && (
          <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            Voice is not fully configured: {voice.config.reason ?? "Missing ElevenLabs configuration."}
          </p>
        )}

        {voice.lastError && (
          <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
            {voice.lastError}
          </p>
        )}
      </div>
    </section>
  );
}
