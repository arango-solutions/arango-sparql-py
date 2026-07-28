---
phase: 04-interoperability-performance-verification
plan: 03
subsystem: docs
tags: [adr, prd, roadmap, requirements, foxx-deprecation, plan-of-record]

# Dependency graph
requires:
  - phase: 04-interoperability-performance-verification (04-01, 04-02)
    provides: perf/tooling scaffolding and OWL format-dispatch groundwork this phase builds on (independent of this plan's docs-only scope)
provides:
  - "ADR-0003: Legacy Foxx parity retired (Foxx deprecated)" — redirect stub + PRD Appendix B.3 body
  - REQ-foxx-parity retired as a v1.0 acceptance gate (was Pending)
  - ROADMAP.md Phase 4 Success Criterion 1 struck
  - PRD §3.7/§13.4 amended to record the retirement; §9.4 SLO table annotated with CI-blocking/Report-only tiers (D-08/D-09)
affects: [phase-04-remaining-plans, phase-08-public-release-readiness]

# Tech tracking
tech-stack:
  added: []
  patterns: ["ADR redirect stub + PRD Appendix B body (mirrors ADR-0001/0002 convention)"]

key-files:
  created:
    - docs/architecture/decisions/0003-foxx-parity-retired.md
  modified:
    - docs/architecture/PRD.md
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md

key-decisions:
  - "REQ-foxx-parity retired (not built) per locked D-01/D-02: legacy Foxx is deprecated, W3C DAWG (>=96.4%) is the sole correctness gate going forward"
  - "PRD Appendix B.3 mirrors the B.2 header shape (Status/Date/Owner/Related) plus Context/Decision/Considered alternatives/Consequences, matching the established ADR convention"
  - "Sec 9.4's 11 SLO rows kept intact (no deletions); each annotated CI-blocking (3 fast in-process rows) or Report-only (8 Docker/LLM/noisy rows) per D-08/D-09"
  - "ROADMAP SC1 kept as a struck-through historical entry (no prior struck-criterion precedent found in ROADMAP.md to follow instead)"

patterns-established:
  - "ADR retirement pattern: redirect stub (docs/architecture/decisions/000N-*.md) + real body in PRD Appendix B.N, cited from every amended cross-reference (§, ROADMAP, REQUIREMENTS)"

requirements-completed: [REQ-foxx-parity]

# Metrics
duration: 10min
completed: 2026-07-28
---

# Phase 4 Plan 03: Foxx-parity retirement (ADR-0003) Summary

**Retired REQ-foxx-parity via a redirect-stub ADR-0003 + PRD Appendix B.3 body, striking ROADMAP Phase 4 SC1 and amending PRD §3.7/§13.4/§9.4 — no Foxx harness, no vendored fixtures, no `tests/legacy_roundtrip/` will be built.**

## Performance

- **Duration:** ~10 min
- **Completed:** 2026-07-28
- **Tasks:** 2
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Authored `docs/architecture/decisions/0003-foxx-parity-retired.md` as an 8-line redirect stub mirroring the ADR-0001 convention exactly
- Added PRD Appendix B.3 (`### B.3 ADR-0003`) with full Status/Date/Owner/Related header, Context, Decision, Considered alternatives, and Consequences sections
- Amended PRD §3.7 acceptance-criteria row: Foxx-parity criterion struck-through and marked WAIVED per ADR-0003
- Replaced PRD §13.4 body with a short historical note: the `tests/legacy_roundtrip/` harness is retired, never built; W3C DAWG (§13.5) is the sole correctness gate
- Annotated all 11 §9.4 SLO rows with a new Tier column (3 CI-blocking in-process rows, 8 Report-only Docker/LLM/noisy rows per D-08/D-09) without deleting any row
- Struck ROADMAP.md Phase 4 Success Criterion 1 with a `STRUCK` annotation citing ADR-0003 (D-01/D-02)
- Marked `.planning/REQUIREMENTS.md` REQ-foxx-parity bullet `RETIRED` (citing ADR-0003/Appendix B.3) and flipped its traceability-table status from `Pending` to `Retired`

## Task Commits

Each task was committed atomically:

1. **Task 1: Author ADR-0003 stub and PRD Appendix B.3 body + §3.7/§13.4/§9.4 amendments** - `79fab1d` (docs)
2. **Task 2: Strike ROADMAP Phase 4 SC1 and mark REQ-foxx-parity Retired** - `6d0fbf7` (docs)

## Files Created/Modified
- `docs/architecture/decisions/0003-foxx-parity-retired.md` - New ADR redirect stub pointing at PRD Appendix B.3
- `docs/architecture/PRD.md` - New Appendix B.3 ADR-0003 body; amended §3.7 acceptance row, §13.4 body (retirement note), §9.4 SLO table (Tier column + tier summary paragraphs)
- `.planning/ROADMAP.md` - Phase 4 Success Criterion 1 struck-through with STRUCK annotation
- `.planning/REQUIREMENTS.md` - REQ-foxx-parity bullet marked RETIRED; traceability-table status flipped Pending -> Retired

## Decisions Made
- Followed the plan's D-01/D-02-locked retirement decisions exactly: no Foxx harness, no vendored fixtures, no `tests/legacy_roundtrip/` module was created.
- Grepped ROADMAP.md for a prior struck-criterion rendering precedent before deciding on the strikethrough + STRUCK-annotation convention; none existed, so the plan's fallback convention (struck-through historical entry, not deleted) was used.
- Added a "Tier" column to the §9.4 SLO table (rather than a per-row footnote) since a column reads more cleanly across all 11 rows and matches the plan's "add a column or per-row footnote" latitude.

## Deviations from Plan

**1. [Rule 1 - Bug] Adjusted ADR-0003 stub wording so the automated verification substring matched**
- **Found during:** Task 1 verification
- **Issue:** The plan's `<verify>` command asserts the literal substring `'Do not add content'` appears in the stub. My first draft wrapped the phrase across a markdown line break (`Do not add\n> content here`), mirroring ADR-0001's own line-wrap — which does not contain that contiguous substring either, but the plan's verify script requires it as one unbroken string.
- **Fix:** Reflowed the sentence so "Do not add content" appears as one contiguous substring, while keeping the overall stub prose and meaning identical to the ADR-0001 pattern.
- **Files modified:** `docs/architecture/decisions/0003-foxx-parity-retired.md`
- **Verification:** Re-ran the plan's Task 1 automated verify command; passed (`ok`).
- **Committed in:** `79fab1d` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug/verify-alignment)
**Impact on plan:** Cosmetic wording fix only, needed to satisfy the plan's own literal-substring verification command. No scope creep.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required. This plan is documentation-only.

## Next Phase Readiness
- REQ-foxx-parity is fully closed (retired) for Phase 4 / v1.0 acceptance purposes; no further Foxx-related work is expected in this phase.
- Remaining Phase 4 plans (third-party tool compat, AOE own-half contract, tiered perf suite) are unaffected by this plan and can proceed independently.
- W3C DAWG query-eval coverage (≥96.4%), the deterministic SPARQL→AQL transpiler, and CI's scripted-only default were all untouched — this was a documentation-only plan.

---
*Phase: 04-interoperability-performance-verification*
*Completed: 2026-07-28*

## Self-Check: PASSED

All created/modified files found on disk; all 3 task/summary commit hashes (`79fab1d`, `6d0fbf7`, `26680a2`) found in git history.
