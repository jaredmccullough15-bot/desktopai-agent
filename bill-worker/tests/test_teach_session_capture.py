from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import teach_session as ts


def test_event_mapping_sequence_redacts_sensitive_fields() -> None:
    events = [
        {
            "event_type": "navigate",
            "url": "https://go.trackvia.com/#/signin",
            "element": {},
        },
        {
            "event_type": "type_text",
            "selector": "input[name='email']",
            "url": "https://go.trackvia.com/#/signin",
            "element": {"name": "email", "text": "Email"},
        },
        {
            "event_type": "type_text",
            "selector": "input[name='password']",
            "url": "https://go.trackvia.com/#/signin",
            "element": {"name": "password", "text": "Password"},
        },
        {
            "event_type": "click",
            "selector": "button:has-text(\"Sign In\")",
            "url": "https://go.trackvia.com/#/signin",
            "element": {"text": "Sign In", "tag": "button"},
        },
        {
            "event_type": "submit",
            "selector": "form#signin",
            "url": "https://go.trackvia.com/#/signin",
            "element": {"tag": "form", "text": "Sign In form"},
        },
    ]

    actions = [ts._event_to_browser_action(evt) for evt in events]

    assert actions[0]["type"] == "navigate"
    assert actions[3]["type"] == "click"
    assert actions[4]["type"] == "submit"

    # Email/password should be treated as sensitive and selector/value hidden.
    for idx in (1, 2):
        assert actions[idx]["type"] == "type"
        assert actions[idx]["selector"] is None
        assert actions[idx]["value_redacted"] == "[redacted]"
        assert actions[idx]["label"] in ("[sensitive]", None)


def test_capture_headers_include_worker_key() -> None:
    headers = ts._teaching_capture_headers("worker-secret")
    assert headers.get("X-Bill-Worker-Key") == "worker-secret"
