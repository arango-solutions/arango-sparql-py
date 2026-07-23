"""The `@pytest.mark.eval` regression gate for the NL -> SPARQL harness.

Runs the no-network `scripted` config through the eval runner and asserts
its live pass-rate meets the checked-in `baseline.json` gate — both the
aggregate pass_rate and, per-case, that nothing which passed at baseline
time now regresses.

Gated behind `RUN_EVAL=1` (rule 200: "eval" is slow and never runs from a
plain `pytest` invocation) so the default local/CI fast path stays quick.
"""

from __future__ import annotations

import json
import os
import pathlib
import re

import pytest

from tests.nl2sparql.eval.runner import CORPUS_PATH, EVAL_DIR, BaselineConfig, _load_corpus, run

pytestmark = pytest.mark.eval

# `not os.getenv("RUN_EVAL")` is falsy for RUN_EVAL=0 (a non-empty string is
# truthy in Python), so a caller intending "eval off" via RUN_EVAL=0 would
# silently get "eval on" instead. Treat "", "0", "false", "no"
# (case-insensitive) as off.
_RUN_EVAL = os.getenv("RUN_EVAL", "").strip().lower() not in ("", "0", "false", "no")


def test_corpus_path_default() -> None:
    """The additive `corpus:` config key must be default-preserving (NL-BENCH-05).

    No-network, always-on test (deliberately NOT gated behind the RUN_EVAL
    skipif -- unlike the sweep-driving tests below, this only exercises
    path-resolution logic, never NlPipeline/a provider). Written BEFORE
    `_load_corpus`/`run()` are changed to accept a `corpus:` path (RESEARCH
    Pitfall 1 -- "the single-hardcoded-corpus.yml trap") so the "existing
    configs behave byte-identically" guarantee is enforced from the first
    commit, not asserted after the fact.
    """
    # `_load_corpus()` (no arg) must equal explicitly loading CORPUS_PATH --
    # the byte-identical default this additive change must never break.
    assert _load_corpus() == _load_corpus(CORPUS_PATH)

    # A config dict lacking a `corpus:` key resolves to today's corpus.yml --
    # this is the exact `config.get("corpus", "corpus.yml")` formula `run()`
    # uses; existing configs (none of which carry a `corpus:` key) must keep
    # resolving here.
    config_without_corpus: dict = {}
    resolved_default = EVAL_DIR / config_without_corpus.get("corpus", "corpus.yml")
    assert resolved_default == CORPUS_PATH

    # A config dict carrying a `corpus:` key resolves to THAT relative path
    # under EVAL_DIR instead -- the mechanism QALD/CK25 configs will use.
    config_with_corpus = {"corpus": "vendored/qald9plus/corpus.yml"}
    resolved_custom = EVAL_DIR / config_with_corpus.get("corpus", "corpus.yml")
    assert resolved_custom == EVAL_DIR / "vendored/qald9plus/corpus.yml"
    assert resolved_custom != CORPUS_PATH


def test_grounding_default_absent_is_noop() -> None:
    """The additive `grounding:` config key must be default-preserving (NL-ACC-01).

    No-network, always-on test (deliberately NOT gated behind the RUN_EVAL
    skipif), mirroring `test_corpus_path_default`'s discipline: it only
    exercises dict-default logic (the exact `config.get("grounding", {})` /
    `.get("k", 0)` formula `run()` uses), never `NlPipeline`/a provider --
    proving every existing config (none of which carry a `grounding:` key)
    keeps resolving to today's zero-shot (no grounding) behavior,
    byte-identical.
    """
    config_without_grounding: dict = {}
    grounding_cfg = config_without_grounding.get("grounding", {})
    assert grounding_cfg == {}
    assert grounding_cfg.get("k", 0) == 0


@pytest.mark.skipif(not _RUN_EVAL, reason="set RUN_EVAL=1 to run the NL eval gate")
def test_scripted_pass_rate_meets_baseline() -> None:
    report = run("scripted")
    baseline = json.loads((EVAL_DIR / "baseline.json").read_text())["configs"]["scripted"]

    # Aggregate regression gate.
    assert report.pass_rate >= baseline["pass_rate"] - 1e-9, (
        f"scripted pass_rate regressed: live={report.pass_rate!r} baseline={baseline['pass_rate']!r}"
    )

    # Per-case regression gate: any case that passed at baseline time must
    # still pass now, catching a swap that keeps the aggregate rate steady
    # while silently breaking a different case.
    live_by_name = {c.name: c.passed for c in report.cases}
    for name, was_passing in baseline["cases"].items():
        if was_passing:
            assert live_by_name.get(name) is True, (
                f"case {name!r} regressed: previously passing per baseline.json, "
                f"now {live_by_name.get(name)!r}"
            )

    # New-case gate: a case added to corpus.yml that isn't yet tracked in
    # baseline.json can't hide a regression behind aggregate dilution (the
    # per-case loop above only ever iterates *known* baseline cases). Every
    # untracked case must pass before it's added to the corpus, forcing the
    # author to consciously add it to baseline.json once green.
    corpus_names = {c.name for c in report.cases}
    baseline_names = set(baseline["cases"])
    new_names = corpus_names - baseline_names
    for name in new_names:
        assert live_by_name.get(name) is True, (
            f"new case {name!r} must pass before it's added to baseline.json (got {live_by_name.get(name)!r})"
        )


@pytest.mark.skipif(not _RUN_EVAL, reason="set RUN_EVAL=1 to run the NL eval gate")
def test_scripted_headroom_invariant() -> None:
    """Scripted headroom SENTINEL + the deliberate-near-miss per-case guard.

    The `0.0 < pass_rate < 1.0` bound is a SENTINEL only: it proves the judge
    CAN fail something on the no-network, key-free path — it is NOT a
    difficulty/headroom measure (one near-miss in a ~25-case corpus is ≈ 0.96,
    so the aggregate bound stays weak as the corpus grows). Genuine headroom is
    a LIVE-config property (Plan 04).

    The REAL guard is the per-case assertion that `deliberate-near-miss` reports
    `passed is False` (AI-SPEC SC2): it fails if the near-miss is removed or
    flipped, so the sentinel cannot be trivially "fixed" by adding passing
    cases — do NOT delete the near-miss to make this go green.
    """
    report = run("scripted")

    # SENTINEL: the judge must be able to both pass and fail something.
    assert 0.0 < report.pass_rate < 1.0, (
        f"scripted pass_rate must stay strictly in (0, 1) as a headroom sentinel; got {report.pass_rate!r}"
    )

    # REAL GUARD (AI-SPEC SC2): the deliberate near-miss must still fail.
    live_by_name = {c.name: c.passed for c in report.cases}
    assert live_by_name.get("deliberate-near-miss") is False, (
        "deliberate-near-miss must report passed=False — it is the real "
        "regression guard keeping baseline.json non-trivial (AI-SPEC SC2); "
        f"got {live_by_name.get('deliberate-near-miss')!r}"
    )


@pytest.mark.skipif(not _RUN_EVAL, reason="set RUN_EVAL=1 to run the NL eval gate")
def test_live_baseline_companion_structural() -> None:
    """No-network structural validation of the live `openai-gpt4o-mini` companion.

    This NEVER makes a network call and NEVER needs a provider key: it only
    inspects the checked-in `baseline.json`. The live companion is folded in by
    a MANUAL, human-reviewed step after a credentialed sweep (AI-SPEC Pitfall 2
    — CI never auto-regenerates it), so before that sweep the entry is absent
    and this test skips, keeping the CI gate green and key-free (SC4).

    Once the companion IS present, validate its shape via `BaselineConfig` and
    assert the reproducibility fields (`model`, `temperature==0.1`,
    `corpus_sha`) are recorded and that the live pass_rate shows genuine
    headroom `0.0 < pass_rate < 1.0` (AI-SPEC SC3 / Critical Failure Mode 2 —
    a near-ceiling live baseline leaves no measurable room for a Phase-7 lift).
    """
    configs = json.loads((EVAL_DIR / "baseline.json").read_text())["configs"]
    if "openai-gpt4o-mini" not in configs:
        pytest.skip(
            "live openai-gpt4o-mini baseline not yet folded into baseline.json "
            "(manual, human-reviewed step after a credentialed sweep; see README.md)"
        )

    entry = configs["openai-gpt4o-mini"]
    # BaselineConfig rejects a malformed companion at parse time (e.g. a
    # pass_rate outside [0, 1] or a missing required aggregate field).
    cfg = BaselineConfig(**entry)

    assert cfg.model, "live baseline must record `model` for reproducibility (Pitfall 6)"
    assert cfg.temperature == 0.1, (
        "live baseline must record temperature=0.1 (hardcoded in "
        f"OpenAICompatibleClient); got {cfg.temperature!r}"
    )
    assert cfg.corpus_sha, (
        "live baseline must pin `corpus_sha` — a pass_rate without a corpus "
        "revision is not reproducible (Critical Failure Mode 4)"
    )
    assert 0.0 < cfg.pass_rate < 1.0, (
        "live baseline must show genuine headroom so a Phase-7 few-shot lift is "
        f"measurable (Critical Failure Mode 2); got {cfg.pass_rate!r}"
    )

    # The companion must never carry a PHANTOM case name the scripted gate
    # doesn't track (that would silently misreport coverage on a case that
    # doesn't exist). It MAY lag behind on newly-added corpus cases, though:
    # the live sweep is a manual, human-run, out-of-band step (`corpus_sha`
    # pins exactly which corpus revision it was measured against), so a
    # corpus.yml case added AFTER the live baseline was captured (e.g.
    # 07.1-03's 9 refusal cases, folded into `scripted` by 07.1-06 without a
    # fresh credentialed re-sweep) is expected to be temporarily absent here
    # — that's a `missing`, not an `extra`, and is NOT a structural defect.
    # (07.1-06 deviation: relaxed from `==` to `<=` — see 07.1-06-SUMMARY.md.)
    scripted_cases = set(configs["scripted"]["cases"])
    assert set(cfg.cases) <= scripted_cases, (
        "live companion `cases` must never carry a case name absent from the "
        f"tracked corpus; extra={set(cfg.cases) - scripted_cases!r}"
    )


@pytest.mark.skipif(not _RUN_EVAL, reason="set RUN_EVAL=1 to run the NL eval gate")
def test_dense_baseline_companion_structural() -> None:
    """No-network structural validation of a folded-in dense baseline entry.

    Mirrors `test_live_baseline_companion_structural` exactly, but for the
    Phase 7 07-04 dense-mode companion(s) (e.g. `openai-gpt4o-mini-dense`).
    This NEVER makes a network call: it only inspects the checked-in
    `baseline.json`. The dense sweep is human-run (Task 4, blocking-human
    checkpoint) and folded in later via a MANUAL, human-reviewed step — so
    before that fold-in no dense entry exists and this test SKIPS, keeping
    the CI gate green and key-free. Once a dense companion IS present,
    validate its shape via `BaselineConfig` and assert the D-04 provenance
    fields are populated and genuine headroom (`0.0 < pass_rate < 1.0`) holds.
    """
    configs = json.loads((EVAL_DIR / "baseline.json").read_text())["configs"]
    dense_names = [name for name in configs if name.endswith("-dense")]
    if not dense_names:
        pytest.skip(
            "no dense baseline entry yet folded into baseline.json "
            "(human-run Task 4 sweep + manual fold-in; see README.md §7)"
        )

    for name in dense_names:
        entry = configs[name]
        cfg = BaselineConfig(**entry)

        assert cfg.embedding_model, f"{name}: missing embedding_model (D-04)"
        assert cfg.embedding_revision, f"{name}: missing embedding_revision (D-04)"
        assert cfg.sentence_transformers_version, f"{name}: missing sentence_transformers_version (D-04)"
        assert 0.0 < cfg.pass_rate < 1.0, (
            f"{name}: dense baseline must show genuine headroom; got {cfg.pass_rate!r}"
        )


@pytest.mark.skipif(not _RUN_EVAL, reason="set RUN_EVAL=1 to run the NL eval gate")
def test_ci_gate_only_ever_runs_scripted() -> None:
    """Static, no-network guard: the eval gate may ONLY invoke `run("scripted")`.

    The live provider must never be reachable from the default (key-free) test
    path (AI-SPEC §6 "No network on the default test path"; T-06.2-11). This
    parses this module's own source and asserts every ``run(...)`` call targets
    the ``scripted`` config — so a future edit that wires the live
    ``openai-gpt4o-mini`` config into the CI gate fails loudly here rather than
    silently posting to a provider during CI. It makes no network call and
    needs no key.
    """
    source = pathlib.Path(__file__).read_text()
    run_targets = re.findall(r"""\brun\(\s*["']([^"']+)["']""", source)

    assert run_targets, "expected at least one run('scripted') call in the eval gate"
    non_scripted = sorted({t for t in run_targets if t != "scripted"})
    assert not non_scripted, (
        "the eval gate must only execute the scripted config on the default "
        f"path; found run() calls for non-scripted config(s): {non_scripted}. "
        "Live sweeps run OUT OF BAND (RUN_EVAL=1 + NL2SPARQL_API_KEY, manual) — "
        "see README.md."
    )
