"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Browser Speech Recognition types (not in all TS lib targets)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySpeechRecognition = any;
type SpeechRecognitionCtor = new () => AnySpeechRecognition;

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | undefined {
  if (typeof window === "undefined") return undefined;
  const w = window as unknown as Record<string, unknown>;
  return (w["SpeechRecognition"] ?? w["webkitSpeechRecognition"]) as SpeechRecognitionCtor | undefined;
}

interface UseVoiceOptions {
  onTranscript: (text: string) => void;
}

interface UseVoiceReturn {
  isSupported: boolean;
  isListening: boolean;
  isSpeaking: boolean;
  ttsEnabled: boolean;
  setTtsEnabled: (v: boolean) => void;
  startListening: () => void;
  stopListening: () => void;
  speak: (text: string) => void;
  cancelSpeech: () => void;
}

export function useVoice({ onTranscript }: UseVoiceOptions): UseVoiceReturn {
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const recognitionRef = useRef<AnySpeechRecognition | null>(null);
  const isSupported =
    typeof window !== "undefined" &&
    ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);

  // initialise recognition once on mount
  useEffect(() => {
    const SR = getSpeechRecognitionCtor();
    if (!SR) return;

    const rec = new SR();
    rec.continuous = false;
    rec.interimResults = false;
    rec.lang = "en-US";
    rec.maxAlternatives = 1;

    rec.onresult = (event: AnySpeechRecognition) => {
      const transcript = (event.results[0]?.[0]?.transcript ?? "") as string;
      if (transcript.trim()) {
        onTranscript(transcript.trim());
      }
      setIsListening(false);
    };

    rec.onerror = () => {
      setIsListening(false);
    };

    rec.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = rec;

    return () => {
      rec.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startListening = useCallback(() => {
    if (!recognitionRef.current || isListening) return;
    try {
      // Rebuild the reference so onTranscript closure picks up latest
      const SR = getSpeechRecognitionCtor();
      if (!SR) return;

      const rec = new SR();
      rec.continuous = false;
      rec.interimResults = false;
      rec.lang = "en-US";
      rec.maxAlternatives = 1;

      rec.onresult = (event: AnySpeechRecognition) => {
        const transcript = (event.results[0]?.[0]?.transcript ?? "") as string;
        if (transcript.trim()) {
          onTranscript(transcript.trim());
        }
        setIsListening(false);
      };

      rec.onerror = () => setIsListening(false);
      rec.onend = () => setIsListening(false);

      recognitionRef.current = rec;
      rec.start();
      setIsListening(true);
    } catch {
      setIsListening(false);
    }
  }, [isListening, onTranscript]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  const speak = useCallback(
    (text: string) => {
      if (!ttsEnabled || typeof window === "undefined" || !window.speechSynthesis) return;
      // Cancel any ongoing speech
      window.speechSynthesis.cancel();
      // Strip markdown-style formatting
      const clean = text
        .replace(/\*\*(.*?)\*\*/g, "$1")
        .replace(/\*(.*?)\*/g, "$1")
        .replace(/`(.*?)`/g, "$1")
        .replace(/#{1,6}\s/g, "")
        .trim();

      if (!clean) return;

      const utterance = new SpeechSynthesisUtterance(clean);
      utterance.rate = 1.05;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;

      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => setIsSpeaking(false);

      window.speechSynthesis.speak(utterance);
    },
    [ttsEnabled],
  );

  const cancelSpeech = useCallback(() => {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
  }, []);

  return {
    isSupported,
    isListening,
    isSpeaking,
    ttsEnabled,
    setTtsEnabled,
    startListening,
    stopListening,
    speak,
    cancelSpeech,
  };
}
