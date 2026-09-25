"""K.10 — Page-state macros (chassis v0.6.4).

Verifies the three reusable page-state partials in
`app/templates/components/_states.html` render the contract documented
in `docs/STATE-HANDLING.md`:

  - loading: `role="status"` + `aria-live="polite"` + visible message
  - empty:   `usa-alert--info` + optional CTA
  - error:   `role="alert"` + `usa-alert--error` + recovery path

These are NOT exhaustive UI tests — they assert the structural
contract that slot code and the wizard's chassis facilitation override
both depend on. If a future chassis bump changes the USWDS class names,
this test flags it before slot code breaks downstream.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Resolve templates dir relative to the chassis source root (not test cwd).
_TEMPLATES_DIR = Path(__file__).parent.parent / "app" / "templates"


def _env() -> Environment:
    """Build a Jinja env that can locate the chassis components/ dir."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def _render(macro_call: str) -> str:
    """Render a one-shot template that imports + invokes a state macro.

    macro_call is a Jinja expression like 'state_loading()' — the helper
    wraps it in '{{ ... }}' so Jinja actually evaluates the macro
    instead of treating it as plain text.
    """
    env = _env()
    macro_name = macro_call.split("(")[0]
    src = (
        "{% from 'components/_states.html' import " + macro_name + " %}"
        "{{ " + macro_call + " }}"
    )
    tpl = env.from_string(src)
    return tpl.render()


# ─── Loading ──────────────────────────────────────────────────────────


def test_state_loading_has_status_role() -> None:
    """Screen readers MUST be able to announce loading without interrupting
    the user's current focus. role='status' + aria-live='polite' is the
    Section 508 contract for non-blocking announcements.
    """
    html = _render('state_loading()')
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html


def test_state_loading_has_visible_text() -> None:
    """Icon-only loading indicators are a Section 508 failure. The macro
    MUST emit visible 'Loading…' (or a custom message) text.
    """
    html = _render('state_loading()')
    assert "Loading" in html, "loading macro must include visible text"


def test_state_loading_accepts_custom_message() -> None:
    """Long-running operations sometimes need a more specific message
    (e.g., 'Generating report — about 30 seconds…'). The macro must
    accept and render it.
    """
    html = _render('state_loading(message="Generating report…")')
    assert "Generating report" in html


# ─── Empty ────────────────────────────────────────────────────────────


def test_state_empty_uses_info_variant() -> None:
    """Empty is not an error — it's the natural starting state for any new
    user. USWDS --info variant communicates 'no action needed yet',
    --error would mislead.
    """
    html = _render('state_empty(message="No items yet.")')
    assert "usa-alert--info" in html
    assert "usa-alert--error" not in html
    assert "No items yet" in html


def test_state_empty_renders_optional_cta() -> None:
    """The CTA slot is optional (some empty contexts are read-only). When
    both cta_url and cta_label are supplied, the macro renders an
    actionable link.
    """
    html = _render(
        'state_empty(message="No items yet.", cta_url="/new", cta_label="Create one")'
    )
    assert 'href="/new"' in html
    assert "Create one" in html


def test_state_empty_omits_cta_when_unset() -> None:
    """Read-only empty contexts (no user permission to create) must NOT
    render a dangling/empty link.
    """
    html = _render('state_empty(message="No payroll runs available.")')
    assert "<a " not in html, "empty state without CTA must not render an anchor"


# ─── Error ────────────────────────────────────────────────────────────


def test_state_error_has_alert_role() -> None:
    """Error states MUST interrupt the user (vs the polite 'status' role
    for loading). role='alert' is the contract.
    """
    html = _render('state_error(message="Could not load section.")')
    assert 'role="alert"' in html


def test_state_error_uses_error_variant() -> None:
    """USWDS --error variant communicates urgency visually (red). Slot
    code must not use --info or --warning for true errors.
    """
    html = _render('state_error(message="Could not load section.")')
    assert "usa-alert--error" in html


def test_state_error_renders_optional_retry() -> None:
    """When a recovery path is supplied, the macro renders a clickable
    secondary button — never the raw exception. The K.8 canonical
    `message_for_status` is the source of the message string.
    """
    html = _render(
        'state_error(message="Could not load section.", retry_url="/dashboard")'
    )
    assert 'href="/dashboard"' in html
    assert "Try again" in html
