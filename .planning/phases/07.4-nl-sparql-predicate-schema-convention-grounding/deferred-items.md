# Deferred Items — Phase 07.4

## Plan 02

- **Pre-existing `ruff format` drift on `grounding_prompt_section` (seam 6) signatures**
  in `arango_sparql/nl2sparql/adapter.py` and `arango_sparql/nl2sparql/engine_adapter.py`.
  `uv run ruff format --check` flags these two files because the seam-6
  `grounding_prompt_section(self, question: str, index: LabelIndex, k: int = 20) -> str:  # seam 6 (renderer)`
  signature line exceeds ruff's wrap width under the currently-installed `ruff==0.15.22`
  formatter. This line was NOT touched by Plan 02 (verified via `git diff` — zero overlap
  with Plan 02's diff hunks) and predates this plan. Out of scope per the executor's
  scope-boundary rule (only auto-fix issues directly caused by the current task's changes).
  Plan 02's own additions (the new `predicate_index()`/`predicate_prompt_section()` methods)
  are format-clean under the same formatter (verified: `ruff format --diff` shows zero
  hunks touching the new predicate methods). Left as-is; a future formatting-only cleanup
  plan/commit can reformat both seam-6 signatures if desired.
