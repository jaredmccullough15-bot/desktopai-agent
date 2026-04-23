"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export type BillVoiceConfig = {
  voice_enabled: boolean;
  configured: boolean;
  reason?: string | null;
  voice_id_present: boolean;
  model_id: string;
  output_format: string;
  default_style_profile: string;
  supported_style_profiles: string[];
  supported_emotions: string[];
  stream_supported: boolean;
  event_voice_enabled: boolean;
  enabled_event_categories: string[];
};

export type BillVoiceSpeakPayload = {
  text: string;
  emotion?: string;
  style_profile?: string;
  task_id?: string;
  workflow_name?: string;
  context?: Record<string, unknown>;
  stream?: boolean;
  voice_settings_override?: Record<string, number | boolean>;
};

export type BillVoiceEventPayload = {
  event_type: string;
  task_id?: string;
  workflow_name?: string;
  context?: Record<string, unknown>;
  override_text?: string;
};

export type BillVoiceMeta = {
  emotion?: string;
  style?: string;
  outputFormat?: string;
  durationMs?: number;
  truncated?: boolean;
};

export type UseBillVoiceReturn = {
  config: BillVoiceConfig | null;
  loadingConfig: boolean;
  loadingAudio: boolean;
  isPlaying: boolean;
  lastError: string | null;
  lastMeta: BillVoiceMeta | null;
  refreshConfig: () => Promise<void>;
  speakText: (payload: BillVoiceSpeakPayload) => Promise<boolean>;
  previewStyle: (payload: BillVoiceSpeakPayload) => Promise<boolean>;
  speakEvent: (payload: BillVoiceEventPayload) => Promise<boolean>;
  stopPlayback: () => void;
};

function toErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Unknown voice error";
}

function buildUrl(apiBase: string, path: string): string {
  return `${apiBase.replace(/\/$/, "")}${path}`;
}

export function useBillVoice(apiBase: string): UseBillVoiceReturn {
  const [config, setConfig] = useState<BillVoiceConfig | null>(null);
  const [loadingConfig, setLoadingConfig] = useState(false);
  const [loadingAudio, setLoadingAudio] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [lastMeta, setLastMeta] = useState<BillVoiceMeta | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  const stopPlayback = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  useEffect(() => () => stopPlayback(), [stopPlayback]);

  const refreshConfig = useCallback(async () => {
    setLoadingConfig(true);
    setLastError(null);
    try {
      const res = await fetch(buildUrl(apiBase, "/api/voice/config"));
      const body = (await res.json()) as BillVoiceConfig & { detail?: string };
      if (!res.ok) {
        throw new Error(body.detail ?? `Voice config request failed (${res.status})`);
      }
      setConfig(body);
    } catch (err) {
      setLastError(toErrorMessage(err));
      setConfig(null);
    } finally {
      setLoadingConfig(false);
    }
  }, [apiBase]);

  useEffect(() => {
    void refreshConfig();
  }, [refreshConfig]);

  const playAudioResponse = useCallback(async (res: Response): Promise<boolean> => {
    if (!res.ok) {
      let detail = `Voice request failed (${res.status})`;
      try {
        const data = (await res.json()) as { detail?: string };
        if (data.detail) detail = data.detail;
      } catch {
        // ignore JSON parsing failures
      }
      throw new Error(detail);
    }

    const blob = await res.blob();
    if (!blob.size) {
      throw new Error("Voice response returned empty audio");
    }

    stopPlayback();

    const objectUrl = URL.createObjectURL(blob);
    objectUrlRef.current = objectUrl;

    const audio = new Audio(objectUrl);
    audioRef.current = audio;
    audio.onended = () => {
      setIsPlaying(false);
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      audioRef.current = null;
    };
    audio.onerror = () => {
      setIsPlaying(false);
      setLastError("Browser failed to play generated voice audio");
    };

    setLastMeta({
      emotion: res.headers.get("X-Bill-Voice-Emotion") ?? undefined,
      style: res.headers.get("X-Bill-Voice-Style") ?? undefined,
      outputFormat: res.headers.get("X-Bill-Voice-Output-Format") ?? undefined,
      durationMs: Number(res.headers.get("X-Bill-Voice-Duration-Ms") ?? "0") || undefined,
      truncated: (res.headers.get("X-Bill-Voice-Truncated") ?? "false") === "true",
    });

    setIsPlaying(true);
    await audio.play();
    return true;
  }, [stopPlayback]);

  const requestAudio = useCallback(async (path: string, payload: Record<string, unknown>): Promise<boolean> => {
    setLoadingAudio(true);
    setLastError(null);
    try {
      const res = await fetch(buildUrl(apiBase, path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return await playAudioResponse(res);
    } catch (err) {
      setLastError(toErrorMessage(err));
      setIsPlaying(false);
      return false;
    } finally {
      setLoadingAudio(false);
    }
  }, [apiBase, playAudioResponse]);

  const speakText = useCallback(async (payload: BillVoiceSpeakPayload): Promise<boolean> => {
    if (!payload.text?.trim()) {
      setLastError("Voice text is required");
      return false;
    }
    return requestAudio("/api/voice/speak", { ...payload, text: payload.text.trim() });
  }, [requestAudio]);

  const previewStyle = useCallback(async (payload: BillVoiceSpeakPayload): Promise<boolean> => {
    if (!payload.text?.trim()) {
      setLastError("Preview text is required");
      return false;
    }
    return requestAudio("/api/voice/preview-style", {
      text: payload.text.trim(),
      emotion: payload.emotion,
      style_profile: payload.style_profile,
      context: payload.context,
      voice_settings_override: payload.voice_settings_override,
    });
  }, [requestAudio]);

  const speakEvent = useCallback(async (payload: BillVoiceEventPayload): Promise<boolean> => {
    if (!payload.event_type?.trim()) {
      setLastError("Event type is required");
      return false;
    }
    return requestAudio("/api/voice/speak-event", {
      event_type: payload.event_type.trim(),
      task_id: payload.task_id,
      workflow_name: payload.workflow_name,
      context: payload.context,
      override_text: payload.override_text,
    });
  }, [requestAudio]);

  return useMemo(() => ({
    config,
    loadingConfig,
    loadingAudio,
    isPlaying,
    lastError,
    lastMeta,
    refreshConfig,
    speakText,
    previewStyle,
    speakEvent,
    stopPlayback,
  }), [
    config,
    loadingConfig,
    loadingAudio,
    isPlaying,
    lastError,
    lastMeta,
    refreshConfig,
    speakText,
    previewStyle,
    speakEvent,
    stopPlayback,
  ]);
}
