# Task 14: Analytics (Frontend)

## Task ID
P14-001

## Feature
Personal Usage Dashboard — Stat Cards, Period-Selectable Line/Bar Charts, Most-Used Features

## Objective
Deliver the frontend for `FR-ANALYTICS-001` per the approved frontend implementation plan's Phase 14 entry: a personal usage dashboard with compact stat cards (documents processed, storage used, AI requests), two minimal flat charts (documents-over-time as a line, AI requests-over-time as a bar) with a 7d/30d/90d period selector, and a most-used-features list — reachable from the sidebar. Built against `api.md`'s `/analytics/dashboard` contract, reusing the existing `UsageStrip` component, and tested against the real (currently backend-less) BFF proxy, consistent with every prior frontend phase. `FR-ANALYTICS-002` (P2, per-document insights) is explicitly out of scope this phase per the roadmap's own framing ("optional in this phase").

## Specification References
- `requirements.md` §1.11 (`FR-ANALYTICS-001`; `FR-ANALYTICS-002` P2, not built this phase) — the requirement set this task targets.
- `ui-ux.md` §13 (Analytics) — **amended twice during this task** (see Implementation Notes); this task's UI contract.
- `api.md` §9 (`/analytics/dashboard`) — no gap found; the single-endpoint shape directly drove one of the two `ui-ux.md` corrections.
- `database.md` §6 — confirms aggregation is computed at query time from `documents`/`ai_requests`, no dedicated analytics table for MVP (informs why there's only one endpoint, not one per section).
- `decisions.md` — **ADR-018 added during this task** (see Implementation Notes) — the charting library choice, flagged as an open decision since the original frontend plan and left unresolved until this phase needed it.

## Requirements
- `FR-ANALYTICS-001` (P1): Personal dashboard showing documents processed over time, storage used, AI requests made, and most-used features.

## Dependencies
- Phases 4–13 (aggregates data produced by every prior feature phase's usage — documents, chat, summarization, extraction, comparison, search).
- Phase 1 (Frontend Foundation) — reuses `UsageStrip` (built for Dashboard) rather than a second storage-quota display.

## Files Affected
- `specs/decisions.md` — modified — added **ADR-018: Frontend charting library — Recharts** (see Implementation Notes).
- `specs/ui-ux.md` — modified — §13 Analytics: corrected the per-section error-state claim to match the API's single-endpoint reality, and corrected the stat-card grid's reflow column count from 4 to 3 (see Implementation Notes).
- `package.json` — modified — added `recharts` (^3.8.0) per ADR-018.
- `components/ui/chart.tsx` — new — shadcn's standard chart primitives (`ChartContainer`/`ChartTooltip`/`ChartLegend`), added via the shadcn CLI, no Radix dependency.
- `lib/api/analytics.ts` — new — typed `getAnalyticsDashboard()` and result types.
- `hooks/use-analytics.ts` — new — `useAnalyticsDashboardQuery` (`keepPreviousData` for period-switch, no flicker).
- `components/domain/analytics/{stat-card,period-selector,line-chart,bar-chart,chart-data-table,most-used-features-list}.tsx` — new.
- `app/(dashboard)/analytics/analytics-view.tsx` — new — period-URL-state + stat cards + charts + features list, single shared loading/error/empty state.
- `app/(dashboard)/analytics/page.tsx` — modified — wired `AnalyticsView` in a `<Suspense>` boundary (was `PhasePlaceholder`).
- Tests: `components/domain/analytics/{stat-card,period-selector,most-used-features-list,chart-data-table,line-chart,bar-chart}.test.tsx`.
- `e2e/analytics.spec.ts` — new.

## Implementation Notes
- **ADR written before implementation, per `CLAUDE.md` rule 4:** the frontend plan explicitly flagged the Analytics charting library as an undecided architectural choice ("a minimal charting library for Analytics ... is not [selected]. None are in `decisions.md`'s ADR list yet"). Resolved as **ADR-018: Recharts, via shadcn's `chart.tsx` wrapper** — chosen over visx (too low-level for two charts), Nivo (gradient-heavy defaults fight the "flat, no 3D/gradient" requirement), and canvas-based libraries (no DOM nodes for the required accessible fallback). Added via the shadcn CLI (`npx shadcn add chart`) exactly like every other `components/ui/*` primitive in this codebase; verified it has no Radix dependency, so it drops into this Base UI-based project with zero friction.
- **Spec gap resolved — per-section error framing didn't match the single-endpoint API:** `ui-ux.md` originally said "a stat-card fetch failure doesn't block the charts from rendering," implying independent per-section fetches. But `api.md` §9 defines exactly one endpoint, `GET /analytics/dashboard`, returning every section in one response — there is no way for stat cards and charts to fail independently. Corrected the spec to describe the real behavior: one inline retry for the whole dashboard, never a full-page error, never blocking the rest of the app.
- **Spec gap resolved — stat-card count didn't match the API response:** `ui-ux.md`'s Layout bullet names exactly three metrics (documents processed, storage used, AI requests), but the Responsive bullet said the grid reflows "4→2→1" — an internal inconsistency, not a real 4th metric anywhere in `api.md`'s response shape. Corrected to "3→2→1," matching the three real `StatCard`s built.
- **`UsageStrip` reused, not rebuilt:** the frontend plan explicitly lists `UsageStrip` under the Analytics domain's components as "(shared with Dashboard/Settings)" — rendered here via the exact same component and `useUsageQuery` hook built in Phase 1, not a second storage-quota display.
- **Chart type mapping is a deliberate, spec-compliant choice, not a hidden default:** `ui-ux.md` names both chart types ("line/bar") without mandating which metric uses which. Documents-over-time renders as a line (trend emphasis); AI requests-over-time renders as a bar (discrete daily counts) — using both named chart types rather than defaulting to one everywhere.
- **"Flat, no 3D/gradient decoration" enforced at the wrapper, not per call site:** `AnalyticsLineChart`/`AnalyticsBarChart` hard-code a solid stroke/fill (no `<defs>` gradients, no drop shadows) and `isAnimationActive={false}` — the latter also means the charts respect reduced-motion universally by never animating, a stronger and simpler guarantee than a conditional `prefers-reduced-motion` check.
- **Accessible chart equivalent:** every chart pairs with a visually-hidden (`sr-only`) `ChartDataTable` exposing the identical series as real `<table>` rows with a caption — `ui-ux.md`'s "text/table equivalent... not visual-only data" requirement — and the visual chart itself is `aria-hidden="true"` so screen readers see the table, not a confusing empty SVG description.
- **Recharts renders correctly in jsdom** with `ChartContainer`'s built-in `initialDimension` fallback (320×200) — no `ResizeObserver` polyfill needed for the components under test in this task (unlike Phase 12/13's `cmdk`-based `Command` popovers), confirmed empirically before committing to that assumption in the test files.

## Tests
- `components/domain/analytics/stat-card.test.tsx` — renders label/value; skeleton shows no data text.
- `components/domain/analytics/period-selector.test.tsx` — active period marked `aria-pressed`; clicking calls `onChange` with the right value.
- `components/domain/analytics/most-used-features-list.test.tsx` — known feature keys humanize to display names; an unrecognized key still gets a readable (title-cased) label, never a raw slug.
- `components/domain/analytics/chart-data-table.test.tsx` — every data point renders as a real table row with a caption.
- `components/domain/analytics/{line-chart,bar-chart}.test.tsx` — renders without throwing; the accessible data table is present alongside the visual chart.
- E2E (`e2e/analytics.spec.ts`, 2 tests): a real connectivity error (not a blank dashboard) with a working retry; the period selector remains usable and updates the URL even while the dashboard can't load. Both exercise the real backend-less BFF, per the established no-mocks pattern for E2E.

## Acceptance Criteria
(Adapted from `requirements.md` §1.11, frontend-observable subset)
- Given usage activity exists, then the dashboard shows documents processed, storage used, and AI-requests stat cards, plus documents-over-time and AI-requests-over-time charts and a most-used-features list.
- Given the user changes the period selector (7d/30d/90d), then all sections re-fetch for that period without a full page reload, and the URL reflects the selection.
- Given a new account with no activity, then the page shows an explanatory "nothing to show yet" message instead of zeroed/broken-looking charts.
- Given no reachable backend, the dashboard shows one inline retry, never a blank page or a full-page crash.
- Given a screen-reader user, each chart has an accessible table equivalent with the same data.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (157/157 Vitest, 55/55 Playwright — one pre-existing, documented parallel-load flake in `dashboard-shell.spec.ts` unrelated to this task, confirmed passing in isolation)
- [x] No requirement silently changed or reinterpreted — both `ui-ux.md` corrections and the charting-library ADR were resolved explicitly, with rationale, before/alongside implementation
- [x] `specs/decisions.md` (ADR-018) and `specs/ui-ux.md` updated — the spec changes this task required
- [x] Browser QA performed at desktop/mobile via mocked-network screenshots (real-BFF interactive states aren't reachable, consistent with prior phases); populated dashboard, empty state, and mobile reflow all verified rendering correctly with flat, non-decorative charts
- [x] Regression check performed across Phases 1–13 (navigation, auth, documents, chat, summarization, extraction, comparison, search, forms, API interactions, shared components, responsive layouts) — no regressions found; backend pytest 87/87, Docker Compose healthy
- [x] Basic performance review performed — the new `recharts` dependency (documented trade-off in ADR-018) is isolated to the `/analytics` route via Next.js code-splitting; `keepPreviousData` avoids a loading flash on period changes; charts disable mount animation (`isAnimationActive={false}`), reducing unnecessary JS work and satisfying reduced-motion universally
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)
