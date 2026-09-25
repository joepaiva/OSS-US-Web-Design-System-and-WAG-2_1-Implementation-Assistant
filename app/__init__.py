"""autonomous-platform-chassis-python — Stack Template #1."""

from __future__ import annotations

from pathlib import Path

#: App package version (semver from pyproject.toml). Per-generated-app.
__version__ = "0.1.0"

# The chassis *framework* version is the single source of truth in the
# CHASSIS_VERSION file at the chassis root (kept in lockstep with the
# platform's Go seed pin; CI enforces equality). It is distinct from
# __version__ above, which is the app package version. The file ships into
# the image via the Dockerfile's `COPY . .` (WORKDIR /app), one directory
# above this package.
_CHASSIS_VERSION_FILE = Path(__file__).resolve().parent.parent / "CHASSIS_VERSION"


def _read_chassis_version() -> str:
    """Read the chassis framework version from CHASSIS_VERSION.

    Falls back to the app version if the file is missing or unreadable, so
    the /version endpoint and System Health page never break on a packaging
    quirk.
    """
    try:
        return _CHASSIS_VERSION_FILE.read_text(encoding="utf-8").strip() or __version__
    except OSError:
        return __version__


#: Chassis framework version (e.g. "0.10.0"), distinct from __version__.
__chassis_version__ = _read_chassis_version()
