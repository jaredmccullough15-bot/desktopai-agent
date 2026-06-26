from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

EmotionName = Literal[
    "neutral",
    "helpful",
    "empathetic",
    "alert",
    "confident",
    "apologetic",
    "excited",
    "frustrated_but_professional",
]

StyleProfileName = Literal[
    "default",
    "calm",
    "energetic",
    "urgent",
    "empathetic",
]


class VoiceSpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    emotion: EmotionName | None = None
    style_profile: StyleProfileName | None = None
    task_id: str | None = None
    workflow_name: str | None = None
    context: dict[str, Any] | None = None
    stream: bool = False
    voice_settings_override: dict[str, float | bool] | None = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("text cannot be empty")
        return cleaned


class VoicePreviewStyleRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    emotion: EmotionName | None = None
    style_profile: StyleProfileName | None = None
    context: dict[str, Any] | None = None
    voice_settings_override: dict[str, float | bool] | None = None


class VoiceEventSpeakRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=120)
    task_id: str | None = None
    workflow_name: str | None = None
    context: dict[str, Any] | None = None
    override_text: str | None = None


class VoiceConfigResponse(BaseModel):
    voice_enabled: bool
    configured: bool
    reason: str | None = None
    voice_id_present: bool
    model_id: str
    output_format: str
    default_style_profile: str
    supported_style_profiles: list[str]
    supported_emotions: list[str]
    stream_supported: bool
    event_voice_enabled: bool
    enabled_event_categories: list[str]


class GeneratedSpeechResult(BaseModel):
    audio_bytes: bytes
    content_type: str = "audio/mpeg"
    output_format: str
    voice_id: str
    model_id: str
    emotion: str
    style_profile: str
    transformed_text: str
    instructions: str
    truncated: bool
    duration_ms: int
    stream_supported: bool = True


class VoiceEventPayload(BaseModel):
    event_type: str
    category: str
    text: str
    emotion: EmotionName
    style_profile: StyleProfileName
