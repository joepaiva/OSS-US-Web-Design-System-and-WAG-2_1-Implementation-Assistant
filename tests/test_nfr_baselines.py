"""K.11 — NFR baselines (chassis v0.6.5).

Tone gate. Asserts that `docs/NFR-BASELINES.md` exists and contains the
five canonical headings the wizard's chassis facilitation override
(Requirements Enumeration) refers to by name. If a future chassis
maintainer deletes a baseline section without a chassis-version bump,
this test fails — that's the point.

Lightweight on purpose: enforcement of the actual NFR targets (Lighthouse
mobile, k6 load test, uptime monitor) belongs in the deploy pipeline,
not the chassis unit suite. This test only proves the policy *exists*
where the override expects to find it.
"""

from __future__ import annotations

from pathlib import Path

# Resolve doc path relative to the chassis source root (not test cwd).
_DOC = (
    Path(__file__).parent.parent
    / "docs"
    / "NFR-BASELINES.md"
)


def test_nfr_baselines_doc_exists() -> None:
    """The doc is the source of truth referenced by both the wizard's
    chassis_requirements_enumeration_override.md topic table and the
    StackTemplate's `chassisBaselineConstitutionNFRBaselines()` Go
    helper. Deleting it would break two parts of the system silently.
    """
    assert _DOC.exists(), f"NFR-BASELINES.md missing at {_DOC}"


def test_nfr_baselines_contain_all_five_topics() -> None:
    """The wizard's override topic table names these five topics:
        nfr_page_load
        nfr_api_response
        nfr_availability
        nfr_concurrent_users
        nfr_data_integrity

    The doc MUST contain a section heading for each. If a topic is
    renamed or removed without a chassis-version bump + override-table
    update, this test catches the drift.
    """
    content = _DOC.read_text(encoding="utf-8")
    required_headings = {
        "Page Load",
        "API Response",
        "Availability",
        "Concurrent Users",
        "Data Integrity",
    }
    missing = {h for h in required_headings if f"## {h}" not in content}
    assert not missing, f"NFR-BASELINES.md missing canonical sections: {missing}"
