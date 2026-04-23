"use client";

import { useCallback, useMemo, useRef, useState } from "react";

export type UseBillMicReturn = {
  supported: boolean;
  permission: PermissionState | "unknown";
  isRecording: boolean;
  requestPermission: () => Promise<boolean>;
  startRecording: () => Promise<boolean>;
  stopRecording: () => Blob | null;
};

export function useBillMic(): UseBillMicReturn {
  const [permission, setPermission] = useState<PermissionState | "unknown">("unknown");
  const [isRecording, setIsRecording] = useState(false);
  const chunksRef = useRef<BlobPart[]>([]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);

  const supported = typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined";

  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (!supported) return false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      setPermission("granted");
      return true;
    } catch {
      setPermission("denied");
      return false;
    }
  }, [supported]);

  const startRecording = useCallback(async (): Promise<boolean> => {
    if (!supported || isRecording) return false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (evt: BlobEvent) => {
        if (evt.data.size > 0) chunksRef.current.push(evt.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setPermission("granted");
      setIsRecording(true);
      return true;
    } catch {
      setPermission("denied");
      return false;
    }
  }, [supported, isRecording]);

  const stopRecording = useCallback((): Blob | null => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") return null;
    recorder.stop();
    const parts = chunksRef.current;
    if (!parts.length) return null;
    return new Blob(parts, { type: "audio/webm" });
  }, []);

  return useMemo(() => ({
    supported,
    permission,
    isRecording,
    requestPermission,
    startRecording,
    stopRecording,
  }), [supported, permission, isRecording, requestPermission, startRecording, stopRecording]);
}
