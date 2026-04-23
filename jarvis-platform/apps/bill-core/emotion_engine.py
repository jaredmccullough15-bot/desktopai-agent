from __future__ import annotations

from typing import Any

from voice_schemas import EmotionName, StyleProfileName

SUPPORTED_EMOTIONS: list[str] = [
    "neutral",
    "helpful",
    "empathetic",
    "alert",
    "confident",
    "apologetic",
    "excited",
    "frustrated_but_professional",
]

SUPPORTED_STYLE_PROFILES: list[str] = [
    "default",
    "calm",
    "energetic",
    "urgent",
    "empathetic",
]

VOICE_STYLE_PRESETS: dict[str, dict[str, float | bool]] = {
    "default": {
        "stability": 0.45,
        "similarity_boost": 0.8,
        "style": 0.3,
        "use_speaker_boost": True,
    },
    "calm": {
        "stability": 0.75,
        "similarity_boost": 0.8,
        "style": 0.15,
        "use_speaker_boost": True,
    },
    "energetic": {
        "stability": 0.35,
        "similarity_boost": 0.85,
        "style": 0.75,
        "use_speaker_boost": True,
    },
    "urgent": {
        "stability": 0.55,
        "similarity_boost": 0.9,
        "style": 0.65,
        "use_speaker_boost": True,
    },
    "empathetic": {
        "stability": 0.65,
        "similarity_boost": 0.78,
        "style": 0.4,
        "use_speaker_boost": True,
    },
}

EMOTION_TO_STYLE: dict[str, str] = {
    "neutral": "default",
    "helpful": "calm",
    "empathetic": "empathetic",
    "alert": "urgent",
    "confident": "default",
    "apologetic": "empathetic",
    "excited": "energetic",
    "frustrated_but_professional": "urgent",
}


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split())


def infer_emotion(context: dict[str, Any] | None) -> EmotionName:
    context = context or {}
    status = str(context.get("status") or "").lower()
    issue_type = str(context.get("issue_type") or "").lower()
    event_type = str(context.get("event_type") or "").lower()
    recovery_status = str(context.get("recovery_status") or "").lower()
    warning = bool(context.get("warning") or context.get("risk_detected"))

    joined = " ".join([status, issue_type, event_type, recovery_status])

    if "recovery" in joined and any(k in joined for k in ["stuck", "failed", "needs_human_help", "paused"]):
        return "empathetic"
    if any(k in joined for k in ["warning", "risk", "timeout", "blocked"]) or warning:
        return "alert"
    if any(k in joined for k in ["resolved", "completed", "success", "fixed"]):
        return "confident"
    if any(k in joined for k in ["starting", "queued", "running"]):
        return "helpful"
    return "neutral"


def resolve_emotion_and_style(
    text: str,
    emotion: str | None,
    style_profile: str | None,
    context: dict[str, Any] | None,
) -> tuple[str, str, str, dict[str, float | bool], str]:
    clean_text = _normalize_text(text)
    resolved_emotion = emotion if emotion in SUPPORTED_EMOTIONS else infer_emotion(context)
    resolved_style = style_profile if style_profile in SUPPORTED_STYLE_PROFILES else EMOTION_TO_STYLE.get(resolved_emotion, "default")

    instructions = {
        "neutral": "Use a clear, steady delivery with direct phrasing.",
        "helpful": "Sound supportive and concise, with practical guidance.",
        "empathetic": "Acknowledge the issue calmly and maintain reassuring tone.",
        "alert": "Speak firmly and clearly, prioritize urgency without panic.",
        "confident": "Use decisive tone and confirm positive progress.",
        "apologetic": "Use sincere tone while focusing on next action.",
        "excited": "Use upbeat pace while keeping wording clear.",
        "frustrated_but_professional": "Acknowledge friction but remain composed and solution-focused.",
    }.get(resolved_emotion, "Use a clear, steady delivery.")

    transformed_text = clean_text
    if resolved_emotion == "alert" and not clean_text.lower().startswith("important"):
        transformed_text = f"Important update. {clean_text}"
    elif resolved_emotion == "empathetic" and "i understand" not in clean_text.lower():
        transformed_text = f"I understand this can be frustrating. {clean_text}"
    elif resolved_emotion == "confident" and not clean_text.endswith("."):
        transformed_text = f"{clean_text}."

    return (
        resolved_emotion,
        resolved_style,
        transformed_text,
        dict(VOICE_STYLE_PRESETS.get(resolved_style, VOICE_STYLE_PRESETS["default"])),
        instructions,
    )
