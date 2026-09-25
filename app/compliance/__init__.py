"""Compliance capabilities (chassis-program shared capabilities):

  - app.compliance.inventory   — Platform Health (FR-PLATHEALTH)
  - app.compliance.fisma_audit — FISMA self-audit + report (FR-FISMAAUDIT)

Both are chassis-owned, admin-only capabilities scoped to THIS package's
own dependency tree / control set — never the platform's.
"""

from __future__ import annotations
