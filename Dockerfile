#
# NO `# syntax=` DIRECTIVE, DELIBERATELY (DM-FR-101 rule 5, 2026-09-22). A syntax
# directive makes Docker fetch that BuildKit frontend from Docker Hub BEFORE the
# build starts; the first live Node deploy hung there for 25 minutes and was killed
# by its own timeout. On a host that cannot reach Docker Hub (air-gapped customer
# Azure, a rate-limited runner) the deploy hangs rather than failing fast. Nothing in
# this file needs it — no RUN --mount, no heredoc, no COPY --link. DM-TS-105 fails if
# any deploy template reintroduces one.
# Shared python-fastapi Dockerfile — ONE source of truth, TWO consumers.
#
# 1. App Builder artifact packager (FR-321 amendment): for python-fastapi
#    chassis builds, ArtifactPackager.dockerfileTemplateForChassis selects THIS
#    file and emits it as the artifact's Dockerfile (the go chassis keeps
#    templates/Dockerfile.tmpl). Before the amendment the packager shipped the
#    go chassis Dockerfile for every build, so a python artifact failed to build
#    (the go base image has no python interpreter and no lockfile to copy).
# 2. Deployment Module (DM-FR-009): renderPythonDeployCompose reads THIS file and
#    writes it into the per-(project,org) deploy workspace, overwriting whatever
#    Dockerfile the artifact shipped. With the packager fix this override is now
#    belt-and-suspenders (it also protects pre-fix / externally-uploaded
#    artifacts). Both consumers read the identical file, so they cannot drift.
#    (v2: a .NET / go-gin Dockerfile lands beside this one, selected by the
#    deploy stack registry.)
#
# Mirrors chassis/python-fastapi-*/Dockerfile: uv on python3.12, deps cached from
# pyproject + uv.lock, then source. The compose `command` runs alembic + uvicorn,
# so this image only needs the venv + source on PATH.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

WORKDIR /app

# NO apt layer (DM-FR-095, 2026-09-15). This image installed curl "for container
# healthchecks" that do not exist: every healthcheck in every compose template in
# this repository belongs to db or redis, and the Deployment Module health-gates a
# new instance itself, over HTTP, from the deployer. The Python chassis's own dev
# compose does not use curl either, so this copy was unused on both sides.
#
# If an app healthcheck is ever added to the compose template, curl comes back in
# the SAME commit — the two changes belong together, and DM-TS-071 fails either
# one on its own, in both directions.
#
# psycopg ships a binary wheel, so there is no libpq apt dependency; and dropping
# curl does not take libssl with it, which was the real finding behind Node's own
# version of this decision (DM-FR-091). Verified against this exact base image:
# `python3 -c "import ssl"` reports OpenSSL 3.0.18 with nothing installed.

# Cache deps first — lockfile + pyproject, no source, no project, no dev group.
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev || \
    uv sync --no-install-project --no-dev

# Copy source; install deps again (project itself stays uninstalled — the app
# runs from source, matching the build sandbox).
COPY . .
RUN uv sync --frozen --no-install-project --no-dev || \
    uv sync --no-install-project --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
