# Task 17: Docker Image Hardening (Frontend)

## Task ID
P17-001

## Feature
Frontend Docker Image Hardening — Non-Root Runtime, Baked-In Healthcheck, Vulnerability Scan Closure, Compose Signal Handling

## Objective
Deliver the frontend scope of Phase 17 per the approved frontend implementation plan: "Frontend Dockerfile hardening (dev-parity only — production frontend is Vercel-deployed, not containerized)." Per `roadmap.md` Phase 17's own scope, this fulfills no `FR-*`/`NFR-*` requirement directly — it is operational readiness: a production-grade, minimal, non-root, healthcheck-capable image that builds reproducibly and passes a real vulnerability scan, with the local Compose stack's `frontend` service finalized to use it correctly.

## Specification References
- `roadmap.md` Phase 17 — "Multi-stage Dockerfile hardening, image size/vulnerability scan, Compose healthchecks finalized" — the three concrete tasks this task closes.
- `devops.md` §1 — Docker architecture — **§1.1 added during this task** (see Implementation Notes).
- `devops.md` §7 — secrets-management mechanics (verified compliant, not modified — no secret is baked into the image; `INTERNAL_API_URL`/`NEXT_PUBLIC_API_BASE_URL` in `docker-compose.yml` are non-secret placeholder URLs, per `deployment.md` §5.1).
- `deployment.md` §2 — confirms production frontend is Vercel-deployed, not this container — this Dockerfile serves dev-parity/local-container-verification purposes only, never a production deploy path.

## Requirements
None directly (`roadmap.md` Phase 17: "Requirements fulfilled: None directly — operational readiness").

## Dependencies
- Phase 1 (scaffolded the original `Dockerfile`/Compose `frontend` service this task hardens).
- Effectively runs once all of Phases 1–16's frontend dependencies are known (per `roadmap.md`'s own Phase 17 dependency note), since the image being scanned/hardened is the full, final dependency tree.

## Files Affected
- `frontend/Dockerfile` — modified — runtime-stage hardening (see Implementation Notes).
- `frontend/.dockerignore` — modified — three additional excludes (`tsconfig.tsbuildinfo`, `*.md`, `.vscode`) to keep the build context minimal.
- `docker-compose.yml` — modified — `frontend` service gets `init: true` for clean signal handling; comment clarifies the healthcheck now lives in the Dockerfile, not duplicated here.
- `specs/devops.md` — modified — new §1.1 documenting the two hardening techniques and the `localhost`-vs-`127.0.0.1` healthcheck gotcha, both found by actually running the built image rather than by reading the Dockerfile.

## Implementation Notes

### Multi-stage, non-root baseline — already correct, verified not rebuilt
The existing `Dockerfile` (Phase 1) already had a correct three-stage build (`deps` → `builder` → `runner`) and a non-root `nextjs` user. Verified, not rebuilt from scratch, per this phase's "do not rebuild functionality already completed" instruction.

### Hardening step 1: `apk upgrade --no-cache`
Patches the base `node:22-alpine` image's own system packages to whatever CVE fixes exist upstream as of build time, rather than freezing at the base image tag's original publish state.

### Hardening step 2: remove the base image's bundled npm — a real vulnerability finding, not a hypothetical
`node:22-alpine` ships a full global `npm` install (and npm's own transitive dependencies) even though this container only ever runs `node server.js` — npm is never invoked at runtime. A `docker scout cves` scan of the image **before** this fix found **16 vulnerabilities (1 critical, 8 high, 7 medium) across 6 packages**; every single one traced to `/usr/local/lib/node_modules/npm/node_modules/...` (verified directly: `docker run --rm <image> find / -type d -name tar` etc.), not to anything in Doxly's own dependency tree. Removing `/usr/local/lib/node_modules/npm`, `/usr/local/bin/npm`, `/usr/local/bin/npx` in the `runner` stage brought the scan to **zero vulnerabilities across the image's remaining 98 packages**. Re-verified the container still runs correctly after removal (healthcheck passes, non-root user confirmed, `/` and `/login` serve `200`) — npm's absence has no effect on `node server.js`.

### Hardening step 3: `HEALTHCHECK` baked into the image, not duplicated in Compose
Added a Docker-native `HEALTHCHECK` (`wget --spider` — BusyBox's built-in applet in this base image, no extra package) against the app's own root path, satisfying `roadmap.md`'s "Compose healthchecks finalized" task. `docker-compose.yml`'s `frontend` service does **not** redeclare its own `healthcheck:` block — Compose reads the one baked into the image, avoiding duplicated logic (the `postgres` service still declares its own, because the official `pgvector/pgvector` image doesn't ship one; this project's own image should carry its own).

**A genuine bug found only by running the built image, not by reading the Dockerfile:** the first version of the healthcheck (`wget --spider http://localhost:3000/`) failed consistently — `docker inspect`'s health log showed `"Connection refused"` — even though the exact same server was verifiably serving `200` on the host-mapped port at the same moment. Root cause: Alpine's resolver returns the IPv6 loopback (`::1`) for `localhost` first, but the Next.js server's `HOSTNAME=0.0.0.0` env var only binds the IPv4 wildcard, so a `localhost`-based healthcheck connection-refuses inside the container's own network namespace. Fixed by targeting `127.0.0.1:3000` explicitly. This is exactly the class of bug that only surfaces by actually running the container (`docker run` + `docker inspect .State.Health`), which this task did — the Dockerfile alone reads as correct.

### `docker-compose.yml`: `init: true`
Runs Docker's built-in `tini` as PID 1 for the `frontend` service so `SIGTERM` (`docker compose stop`/`down`) reaches and cleanly shuts down the Next.js server, instead of the container hanging until Compose's stop-timeout force-kills it. No image size cost (uses the Docker daemon's own bundled `docker-init`, nothing added to the image).

### `.dockerignore` — minor build-context cleanup
Added `tsconfig.tsbuildinfo` (a stale local incremental-build cache artifact — never useful inside a fresh container build), `*.md` (documentation, never read at runtime), `.vscode` (editor config, not present in this repo currently but excluded defensively). None of these affected the final image (multi-stage already discarded them via `.next/standalone`'s dependency tracing) — this only shrinks what gets sent to the Docker build context/`builder` stage.

### `frontend` service's Compose role, confirmed unchanged
`deployment.md` §2 confirms production frontend is Vercel-deployed, not this container — this Dockerfile/Compose service exists for local dev-parity and container-correctness verification only (`roadmap.md`'s own Phase 17 framing: "Frontend Dockerfile hardening (dev-parity only...)"). No change to that role this task — the image is not wired into any deploy path (that's Phase 18/19's job).

## Tests
No new automated test files this task (infrastructure-only; Docker images aren't unit/component-testable). Verification was performed by actually running the built artifact:
- `docker build` — succeeds cleanly, all 21 routes compile in the build log.
- `docker run` + `docker inspect .State.Health` — transitions to `"healthy"`.
- `docker exec ... whoami` — confirms `nextjs` (non-root).
- `curl` against `/` and `/login` on the mapped port — both `200`.
- `docker scout cves` — `0C 0H 0M 0L`, down from `1C 8H 7M 0L` before the npm-removal fix.
- `docker compose build frontend` + `docker compose up -d frontend` + `docker compose ps` — shows `Up ... (healthy)`, confirming Compose correctly reads the image's baked-in `HEALTHCHECK`.
- `docker compose down frontend` — clean, immediate stop (confirms `init: true`'s signal handling).
- Full frontend regression suite (no application code changed, run for completeness): Vitest 182/182, Playwright 59/59, `tsc --noEmit` clean, `eslint` clean, `next build` clean (both standalone `npm run build` and inside the Docker build).
- Backend regression: pytest 87/87, Docker Compose `postgres`/`redis` unaffected and healthy throughout.
- Browser QA: the containerized image's `/login` page verified rendering correctly through a real browser, no console errors.

## Acceptance Criteria
(Adapted from `roadmap.md` Phase 17's Definition of Done: "Images pass the CI build/scan gate defined in devops.md" — verified manually here since the CI gate itself is Phase 18's deliverable, not yet wired)
- The frontend image builds successfully via `docker build` and via `docker compose build`.
- The running container reports `healthy` via its own baked-in healthcheck.
- The running process is non-root.
- `docker scout cves` reports zero vulnerabilities.
- `docker compose down` stops the frontend service cleanly and promptly.
- No regression in Phases 1–16's application code, tests, or specs.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Verification performed by actually running the built image (build, run, healthcheck, non-root check, curl, vulnerability scan, Compose integration, teardown) — not inferred from reading the Dockerfile alone; this caught a real bug (the `localhost`/IPv6 healthcheck failure) a static read would have missed
- [x] No requirement silently changed or reinterpreted — Phase 17's scope stayed to the frontend Dockerfile/Compose hardening named in the frontend plan; Vercel Git integration and the Lighthouse CI budget gate (grouped with "17–18" in the frontend plan's display table) were confirmed to belong to Phase 18 per `roadmap.md`'s own separate Phase 17 (Docker) / Phase 18 (CI/CD) definitions, and were not implemented here
- [x] `specs/devops.md` updated (§1.1) — the one spec change this task required, documenting both hardening techniques and the healthcheck gotcha as tribal knowledge for future base-image bumps
- [x] Browser QA performed — the containerized (not `npm run dev`) build verified rendering correctly through a real browser, no console errors
- [x] Full regression check performed across Phases 1–16 — no regressions found; Vitest 182/182, Playwright 59/59, `tsc --noEmit` clean, `eslint` clean, `next build` clean, backend pytest 87/87, Docker Compose (`postgres`/`redis`) healthy throughout
- [x] Security review performed — this phase's entire purpose is security-adjacent hardening; the vulnerability scan is the security review, and it went from a real 1-critical/8-high finding to zero
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

## Known Limitations / Follow-Up (not fixed this task, correctly scoped to later phases)
- **CI-automated build/scan gating is not wired** — `roadmap.md` Phase 17's Definition of Done references a "CI build/scan gate," but no `.github/workflows/` exists yet (confirmed before starting this task) — that's Phase 18 (CI/CD)'s deliverable. This task verified the image manually (build, run, scan) so it's ready to be gated once that CI infrastructure exists, but the automated gate itself is intentionally not built here.
- **Vercel Git integration and the Lighthouse CI budget gate** — named in the frontend plan's combined "17–18" display row, but per `roadmap.md`'s own Phase 17 (Docker) vs. Phase 18 (CI/CD) split, these belong to Phase 18 ("Vercel Git integration" is explicitly listed under Phase 18's Tasks) — not implemented here.
- **Backend/worker Dockerfiles are out of this task's scope** — this is a frontend-implementation-plan execution; the backend/worker images (Phase 1-scaffolded, per `devops.md` §1's service table) were not touched or audited here.
