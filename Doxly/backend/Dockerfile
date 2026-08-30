# Doxly backend — shared FastAPI/worker image (specs/devops.md §1,
# specs/architecture.md §2.3: "same codebase, same dependency layer —
# differing only in the container's entrypoint command"). Multi-stage,
# non-root runtime, matching frontend/Dockerfile's hardening approach
# (roadmap.md Phase 17's objective covered frontend/backend/worker; this
# closes the backend/worker half that Phase 17 left undone — see
# tasks/18-ci-cd.md's Implementation Notes for why it lands here instead).
#
# This image's default CMD runs the FastAPI HTTP server. The background-
# worker entrypoint (`rq worker document_processing extraction comparison
# summary`, app/core/queue.py's four queue names) is this same image with
# its CMD overridden — implemented as of R3/R5/R6/R7 (tasks/remediation-
# plan.md) and exercised by docker-compose.yml's `worker` service. No
# separate Dockerfile for it, per architecture.md §2.3.

FROM python:3.12-slim AS builder
WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# pyproject.toml alone first would normally maximize layer caching, but
# hatchling's build backend (pyproject.toml's [tool.hatch.build.targets.wheel])
# resolves `packages = ["app"]` at install time, so `pip install .` needs the
# package directory present in this same layer regardless — no caching win
# available here without a lockfile-based two-step install, which this
# project doesn't use (no uv.lock/requirements.txt, per pyproject.toml).
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

# Runtime image — non-root, minimal, patched (skills/devops.md: "never bake a
# secret into an image layer"; DATABASE_URL/REDIS_URL/*_API_KEY are supplied
# as environment variables at container start, per specs/deployment.md §5).
FROM python:3.12-slim AS runner
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Patches the base image's own system packages to whatever CVE fixes exist
# upstream as of build time (same rationale as frontend/Dockerfile's
# `apk upgrade`; devops.md §1.1's hardening pattern applied to the debian-slim
# base here instead of alpine), then removes `perl-base` — a real
# `docker scout cves` finding, not a hypothetical: python:3.12-slim ships it
# as a Debian "Essential" package, but nothing this container actually runs
# (uvicorn/the venv) invokes perl, and no other installed package depends on
# it (verified: `apt-cache rdepends --installed perl-base` returns nothing).
# It carried 2 CRITICAL + 1 HIGH CVE with no upstream fix available at build
# time — the same class of "bundled-but-unused base-image weight" finding as
# frontend/Dockerfile's npm removal. Purged only after `addgroup`/`adduser`
# run below — both are themselves Perl scripts on Debian, so perl has to
# still be present for user/group creation and can only go once nothing
# later in this build needs it.
RUN apt-get update \
    && apt-get upgrade -y \
    && addgroup --system --gid 1001 appuser \
    && adduser --system --uid 1001 --gid 1001 --no-create-home appuser \
    && dpkg --purge --force-remove-essential perl-base \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/app ./app
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser alembic.ini ./

USER appuser
EXPOSE 8000

# No curl/wget in python:3.12-slim by design (keeps the image minimal) — the
# healthcheck uses the interpreter that's already there instead of adding a
# package just to probe one endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

# Container platform's deploy config overrides this CMD for the worker
# process (architecture.md §2.3) — see the module docstring above.
#
# Railway pre-deployment verification finding J.1 (tasks/railway-pre-
# deployment-verification.md): Railway injects a PORT environment variable
# and routes traffic to whatever port the process actually listens on —
# a hardcoded port is a real risk on a platform that assigns it, unlike
# docker-compose where the host-port mapping is under our own control.
# `${PORT:-8000}` falls back to 8000 when PORT is unset (a bare `docker
# run` of this image with no PORT set, matching prior behavior exactly)
# and honors Railway's assigned value otherwise. This requires an actual
# shell to expand the `${...}` syntax — exec-form CMD (`["uvicorn", ...]`)
# never invokes one, so a literal `${PORT:-8000}` argument would reach
# uvicorn unexpanded and fail outright. `sh -c` plus `exec` is the same
# graceful-shutdown-preserving pattern docker-compose.yml's `backend`
# command already uses (R12) — `exec` replaces the shell process with
# uvicorn so it still receives a forwarded SIGTERM directly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
