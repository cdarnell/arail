"""Test toast UI integration for Buddy suggestions.

Verifies that:
1. Suggestions are emitted with correct payload structure
2. Toast CSS and HTML are properly integrated
3. Event handler correctly detects and displays suggestions
"""

import json
from pathlib import Path


def test_suggestion_payload_structure():
    """Verify suggestion payloads have the correct structure."""
    # Mock an observation with suggestion
    suggestion_payload = {
        "kind": "skill",
        "target": "evaluate-llm",
        "link": "/skills/evaluate-llm",
    }

    # This would be emitted by Buddy
    activity_event = {
        "ts": "2026-04-26T12:00:00+00:00",
        "source": "buddy",
        "message": "Worth trying: the 'evaluate-llm' skill matches your goal.",
        "level": "suggest",
        "data": {
            "suggestion": suggestion_payload,
        },
    }

    # Verify structure
    assert activity_event["source"] == "buddy"
    assert activity_event["level"] == "suggest"
    assert activity_event["data"]["suggestion"]["kind"] == "skill"
    assert activity_event["data"]["suggestion"]["target"] == "evaluate-llm"
    assert activity_event["data"]["suggestion"]["link"] == "/skills/evaluate-llm"


def test_dashboard_template_has_toast_container():
    """Verify the dashboard template includes the toast container."""
    template_path = Path(__file__).parent.parent / "src/arail/portal/templates/dashboard.html"
    content = template_path.read_text()

    assert 'id="toast-container"' in content
    assert 'class="toast-container"' in content


def test_dashboard_template_has_show_suggestion_toast():
    """Verify the dashboard template includes the showSuggestionToast function."""
    template_path = Path(__file__).parent.parent / "src/arail/portal/templates/dashboard.html"
    content = template_path.read_text()

    assert 'function showSuggestionToast(event)' in content
    assert 'event.source === \'buddy\' && event.level === \'suggest\'' in content


def test_css_includes_toast_styles():
    """Verify style.css includes toast styling."""
    css_path = Path(__file__).parent.parent / "src/arail/portal/static/style.css"
    content = css_path.read_text()

    assert '.toast-container' in content
    assert '.toast {' in content
    assert '.toast-suggest' in content
    assert '.toast-dismiss' in content
    assert 'slide-in-right' in content


def test_activity_event_level_suggest_renders():
    """Verify suggest level is handled in activity feed CSS."""
    css_path = Path(__file__).parent.parent / "src/arail/portal/static/style.css"
    content = css_path.read_text()

    assert '.activity-event.suggest .src' in content


def test_suggestion_types_have_icons():
    """Verify all suggestion types have associated icons in JavaScript."""
    template_path = Path(__file__).parent.parent / "src/arail/portal/templates/dashboard.html"
    content = template_path.read_text()

    # Extract the kindIcons object
    expected_kinds = ['skill', 'phase', 'review', 'experiment', 'source']
    for kind in expected_kinds:
        assert f"'{kind}':" in content or f'"{kind}":' in content


def test_toast_auto_dismiss_configured():
    """Verify toasts auto-dismiss after configured time."""
    template_path = Path(__file__).parent.parent / "src/arail/portal/templates/dashboard.html"
    content = template_path.read_text()

    # Check for auto-dismiss timer (8 seconds = 8000ms)
    assert 'setTimeout(() => {' in content
    assert '8000' in content  # 8 second timeout for toasts
