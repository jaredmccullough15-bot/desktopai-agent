from __future__ import annotations

from teaching_reasoning_service import analyze_teaching_reasoning


def _base_step() -> dict:
    return {
        "id": "step-1",
        "order": 1,
        "title": "Observed browser activity",
        "employee_explanation": "",
        "bill_summary": "",
        "pending_question": None,
        "unanswered_question": False,
        "last_reasoned_at": None,
    }


def _base_session() -> dict:
    return {
        "session_id": "session-1",
        "workflow_name": "Submission",
        "steps": [_base_step()],
    }


def test_navigation_action_creates_summary() -> None:
    result = analyze_teaching_reasoning(
        teaching_session=_base_session(),
        recent_browser_actions=[
            {"type": "navigate", "url": "https://healthsherpa.com/clients"},
        ],
        latest_employee_message="",
        current_step=_base_step(),
    )

    assert "open" in result["bill_summary"].lower()
    assert "clients" in result["bill_summary"].lower()


def test_search_action_triggers_search_input_question() -> None:
    result = analyze_teaching_reasoning(
        teaching_session=_base_session(),
        recent_browser_actions=[
            {"type": "type", "label": "Client search"},
            {"type": "click", "label": "Search"},
        ],
        latest_employee_message="",
        current_step=_base_step(),
    )

    assert result["question"] == "What tells Bill which client to search for?"


def test_submit_action_triggers_presubmit_question() -> None:
    result = analyze_teaching_reasoning(
        teaching_session=_base_session(),
        recent_browser_actions=[
            {"type": "submit", "label": "Submit"},
        ],
        latest_employee_message="",
        current_step=_base_step(),
    )

    assert result["question"] == "What should Bill verify before submitting?"


def test_skip_or_cancel_triggers_skip_condition_question() -> None:
    result = analyze_teaching_reasoning(
        teaching_session=_base_session(),
        recent_browser_actions=[
            {"type": "click", "label": "Skip"},
        ],
        latest_employee_message="I skip this record when the account is inactive",
        current_step=_base_step(),
    )

    assert result["question"] == "When should Bill skip someone?"


def test_repeated_clicks_do_not_interrupt() -> None:
    result = analyze_teaching_reasoning(
        teaching_session=_base_session(),
        recent_browser_actions=[
            {"type": "click", "label": "Next"},
            {"type": "click", "label": "Next"},
            {"type": "click", "label": "Next"},
        ],
        latest_employee_message="",
        current_step=_base_step(),
    )

    assert result["should_interrupt"] is False
    assert result["reason"] == "repeated_clicks_only"


def test_missing_employee_explanation_triggers_explanation_question() -> None:
    step = _base_step()
    step["employee_explanation"] = ""

    result = analyze_teaching_reasoning(
        teaching_session=_base_session(),
        recent_browser_actions=[
            {"type": "navigate", "url": "https://example.com/forms"},
        ],
        latest_employee_message="",
        current_step=step,
    )

    assert result["question"] == "Can you explain this step in simple words?"


def test_technical_selectors_are_not_in_reasoning_output() -> None:
    result = analyze_teaching_reasoning(
        teaching_session=_base_session(),
        recent_browser_actions=[
            {"type": "click", "label": "Submit", "selector": "#submit_button > div:nth-child(2)"},
            {"type": "navigate", "url": "https://example.com/complete"},
        ],
        latest_employee_message="",
        current_step=_base_step(),
    )

    combined = f"{result['bill_summary']} {result['question']}"
    assert "#submit_button" not in combined
    assert "nth-child" not in combined
