from __future__ import annotations

from typing import Any

import requests

APPEND_TIMEOUT = 8


def _post_teaching_context(api_base: str, session_id: str, context_payload: dict[str, Any]) -> tuple[bool, str | None]:
    """Post a teaching context payload without raising on transport/server errors."""
    if not session_id:
        return False, "missing_session_id"

    endpoint = f"{api_base.rstrip('/')}/api/teaching/session/{session_id}/context"
    try:
        resp = requests.post(endpoint, json=context_payload, timeout=APPEND_TIMEOUT)
    except Exception as exc:
        return False, f"request_error: {exc}"

    if resp.status_code == 200:
        return True, None
    return False, f"HTTP {resp.status_code}: {str(resp.text or '').strip()[:200]}"
