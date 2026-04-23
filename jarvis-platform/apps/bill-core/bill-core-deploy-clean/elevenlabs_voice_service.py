from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from emotion_engine import SUPPORTED_EMOTIONS, SUPPORTED_STYLE_PROFILES, resolve_emotion_and_style
from voice_schemas import GeneratedSpeechResult

logger = logging.getLogger("bill-core.voice")

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class VoiceServiceError(Exception):
    pass


@dataclass
class VoiceRuntimeConfig:
    enabled: bool
    configured: bool
    reason: str | None
    api_key_present: bool
    voice_id: str
    model_id: str
    output_format: str
    default_style_profile: str


def _truthy(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_voice_runtime_config() -> VoiceRuntimeConfig:
    enabled = _truthy(os.getenv("BILL_VOICE_ENABLED"), default=True)
    api_key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
    voice_id = (os.getenv("ELEVENLABS_VOICE_ID") or "").strip()

    model_id = (os.getenv("ELEVENLABS_MODEL_ID") or "eleven_multilingual_v2").strip()
    output_format = (os.getenv("ELEVENLABS_OUTPUT_FORMAT") or "mp3_44100_128").strip()
    default_style = (os.getenv("BILL_DEFAULT_VOICE_STYLE") or "default").strip().lower()
    if default_style not in SUPPORTED_STYLE_PROFILES:
        default_style = "default"

    if not enabled:
        return VoiceRuntimeConfig(
            enabled=False,
            configured=False,
            reason="BILL_VOICE_ENABLED is false",
            api_key_present=bool(api_key),
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
            default_style_profile=default_style,
        )

    if not api_key:
        return VoiceRuntimeConfig(
            enabled=True,
            configured=False,
            reason="ELEVENLABS_API_KEY is missing",
            api_key_present=False,
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
            default_style_profile=default_style,
        )

    if not voice_id:
        return VoiceRuntimeConfig(
            enabled=True,
            configured=False,
            reason="ELEVENLABS_VOICE_ID is missing",
            api_key_present=True,
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
            default_style_profile=default_style,
        )

    return VoiceRuntimeConfig(
        enabled=True,
        configured=True,
        reason=None,
        api_key_present=True,
        voice_id=voice_id,
        model_id=model_id,
        output_format=output_format,
        default_style_profile=default_style,
    )


def _truncate_text(text: str, max_chars: int = 1400) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    clipped = text[:max_chars]
    last_period = clipped.rfind(".")
    if last_period > 400:
        clipped = clipped[: last_period + 1]
    return clipped.strip(), True


def _sanitize_voice_settings(raw: dict[str, Any] | None) -> dict[str, float | bool]:
    if not raw:
        return {}
    allowed_float_keys = {"stability", "similarity_boost", "style", "speed"}
    allowed_bool_keys = {"use_speaker_boost"}
    cleaned: dict[str, float | bool] = {}

    for key, value in raw.items():
        if key in allowed_float_keys:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if key != "speed":
                numeric = max(0.0, min(1.0, numeric))
            else:
                numeric = max(0.7, min(1.2, numeric))
            cleaned[key] = numeric
        elif key in allowed_bool_keys:
            cleaned[key] = bool(value)

    return cleaned


def generate_bill_speech(
    text: str,
    emotion: str | None = None,
    voice_settings_override: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    style_profile: str | None = None,
) -> GeneratedSpeechResult:
    config = get_voice_runtime_config()
    if not config.configured:
        raise VoiceServiceError(config.reason or "Voice service is not configured")

    started = time.perf_counter()

    resolved_emotion, resolved_style, transformed_text, preset_settings, instructions = resolve_emotion_and_style(
        text=text,
        emotion=emotion,
        style_profile=style_profile or config.default_style_profile,
        context=context,
    )
    safe_text, truncated = _truncate_text(transformed_text)
    override_settings = _sanitize_voice_settings(voice_settings_override)
    final_voice_settings = {**preset_settings, **override_settings}

    payload: dict[str, Any] = {
        "text": safe_text,
        "model_id": config.model_id,
        "voice_settings": final_voice_settings,
        "output_format": config.output_format,
    }

    if isinstance(context, dict):
        language_code = str(context.get("language_code") or "").strip()
        if language_code:
            payload["language_code"] = language_code

    endpoint = ELEVENLABS_TTS_URL.format(voice_id=config.voice_id)
    headers = {
        "xi-api-key": (os.getenv("ELEVENLABS_API_KEY") or "").strip(),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    logger.info(
        "Voice request started: emotion=%s style=%s text_len=%s truncated=%s",
        resolved_emotion,
        resolved_style,
        len(text),
        truncated,
    )

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=35)
    except requests.RequestException as exc:
        logger.exception("Voice request failed before response: %s", exc)
        raise VoiceServiceError("Voice provider request failed") from exc

    if response.status_code >= 400:
        detail = "unknown"
        try:
            detail = response.text[:500]
        except Exception:
            pass
        logger.error(
            "Voice generation failed: status=%s detail=%s",
            response.status_code,
            detail,
        )
        raise VoiceServiceError(f"Voice generation failed ({response.status_code})")

    audio = response.content
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "Voice request succeeded: bytes=%s duration_ms=%s emotion=%s style=%s",
        len(audio),
        duration_ms,
        resolved_emotion,
        resolved_style,
    )

    return GeneratedSpeechResult(
        audio_bytes=audio,
        content_type="audio/mpeg" if config.output_format.startswith("mp3") else "audio/wav",
        output_format=config.output_format,
        voice_id=config.voice_id,
        model_id=config.model_id,
        emotion=resolved_emotion,
        style_profile=resolved_style,
        transformed_text=safe_text,
        instructions=instructions,
        truncated=truncated,
        duration_ms=duration_ms,
        stream_supported=True,
    )


def get_voice_capabilities() -> dict[str, Any]:
    cfg = get_voice_runtime_config()
    return {
        "voice_enabled": cfg.enabled,
        "configured": cfg.configured,
        "reason": cfg.reason,
        "voice_id_present": bool(cfg.voice_id),
        "model_id": cfg.model_id,
        "output_format": cfg.output_format,
        "default_style_profile": cfg.default_style_profile,
        "supported_style_profiles": SUPPORTED_STYLE_PROFILES,
        "supported_emotions": SUPPORTED_EMOTIONS,
        "stream_supported": True,
    }
