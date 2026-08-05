"""Mapping acquisition (PRD §6.3.2).

Three tiers, in priority order:

1. **Analyzer (canonical).** Wraps
   :class:`schema_analyzer.AgenticSchemaAnalyzer` (the optional
   ``arangodb-schema-analyzer`` package, version pin
   ``>=0.6.1,<0.7``). Produces a :class:`MappingBundle` that mirrors
   the wire shape PRD §6.2 specifies.
2. **Heuristic (fallback).** Calls
   :func:`arango_sparql.schema.detect.build_heuristic_mapping` (Slice
   4) when the analyzer extra is not installed. Attaches a
   ``W_SCHEMA_HEURISTIC_FALLBACK`` warning so downstream consumers
   (UI, NL→SPARQL planner) can degrade gracefully.
3. **RPT enrichment (always).** Runs
   :func:`arango_sparql.schema.detect.detect_rpt_pattern` on top of
   *whichever* tier produced the bundle and merges any
   ``is_rpt=True`` collections into ``physicalMapping.entities`` with
   ``style="RPT"``. The analyzer alone only knows PG/LPG; this pass
   is what gives us correct routing for legacy ``_triples`` layouts
   even when the analyzer is installed (PRD §6.3.2 step 2). The same
   pass then synthesizes ``RPT_EDGE`` relationships for every object
   property in the triples store via
   :func:`arango_sparql.schema.detect.infer_rpt_object_property_relationships`,
   typing each relationship's ``fromEntity`` / ``toEntity`` from the
   subject's and object's ``rdf:type`` — the cross-collection
   inference neither the analyzer (Cypher-centric) nor the bare RPT
   entity overlay performs.

4. **Edge-endpoint enrichment (always).** Runs
   :func:`_apply_edge_endpoint_enrichment` over whichever bundle the
   tiers above produced, filling relationship ``fromEntity`` /
   ``toEntity`` that are still ``"Any"`` by sampling ``_from`` / ``_to``
   (:func:`arango_sparql.schema.detect.infer_edge_endpoints_from_db`).
   Strictly additive — an endpoint a producer already pinned is never
   overwritten — so it closes the analyzer's cross-collection gap
   without fighting it.

Public surface:

* :func:`acquire_mapping_bundle` — the orchestration entry point.
* :func:`analyzer_available` — light probe for the startup guard
  (Slice 6 ``service/app.py`` ``_require_analyzer_unless_opted_out``).
* :func:`db_shape_fingerprint` / :func:`db_counts_fingerprint` —
  thin wrappers around the analyzer's cheap live-DB fingerprints,
  used by the cache layer to decide whether to re-acquire without
  loading a full bundle.

Caching is **not** done here — the route layer (Slice 7) wires a
:class:`SchemaCache` instance and invokes :func:`acquire_mapping_bundle`
on cache miss / drift. Keeping caching out of this module preserves
the "acquisition is a pure function of (db, strategy, include_owl)"
contract that makes the unit tests in ``tests/schema/test_acquire.py``
straightforward.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any, Literal

from arango_sparql.schema.detect import (
    build_heuristic_mapping,
    detect_rpt_pattern,
    infer_edge_endpoints_from_db,
    infer_rpt_object_property_relationships,
)
from arango_sparql.translate.mapping import (
    MappingBundle,
    MappingSource,
    mapping_from_wire_dict,
)

logger = logging.getLogger(__name__)

# PRD line 610: when ``strategy="auto"`` falls back to the heuristic
# path because the analyzer extra is unimportable, attach this code
# to ``metadata.warnings`` so the route layer (Slice 7) can surface
# "you should install arangodb-schema-analyzer" without reading
# ``source.kind``. Distinct from :data:`W_SCHEMA_HEURISTIC_FALLBACK`
# (PRD §6.3.4), which is the bundle's own provenance marker — that
# one is attached by the heuristic builder and is present on every
# heuristic bundle, including those produced by an explicit
# ``strategy="heuristic"`` request.
W_ANALYZER_NOT_INSTALLED: str = "ANALYZER_NOT_INSTALLED"

# Code stamped on a warning that arrived as a *bare string* rather than the
# canonical ``{code, message}`` dict. The analyzer (and some of its
# downstream exporters) emit free-text advisories — e.g. "LLM provider not
# configured, falling back to heuristic baseline inference" — as plain
# strings, but every ``warnings`` field in the wire contract
# (``service/models.py``) is typed ``list[dict]``. Coercing at the bundle
# boundary (:func:`_normalize_bundle_warnings`) keeps that invariant so a
# string advisory cannot 500 the response-model validation.
W_ANALYZER_ADVISORY: str = "W_ANALYZER_ADVISORY"

# Kept for backward-import compat — older slices referenced this
# name. Both codes are emitted on the auto-fallback path: the
# provenance marker and the install hint coexist on the same
# bundle.
W_SCHEMA_HEURISTIC_FALLBACK: str = "W_SCHEMA_HEURISTIC_FALLBACK"

# Pin matches pyproject.toml extras and the README install hint.
# When this gets bumped, update both call sites in lockstep.
ANALYZER_VERSION_RANGE: str = ">=0.6.1,<0.7"
ANALYZER_INSTALL_HINT: str = f"pip install 'arangodb-schema-analyzer{ANALYZER_VERSION_RANGE}'"

Strategy = Literal["auto", "analyzer", "heuristic"]
_VALID_STRATEGIES: tuple[Strategy, ...] = ("auto", "analyzer", "heuristic")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def acquire_mapping_bundle(
    db: Any,
    *,
    include_owl: bool = False,
    strategy: Strategy = "auto",
    force_refresh: bool = False,
    graph_name: str | None = None,
    now: datetime | None = None,
) -> MappingBundle:
    """Acquire a fresh :class:`MappingBundle` for the live database *db*.

    Parameters
    ----------
    db:
        A duck-typed ``StandardDatabase``-like handle. Must expose
        ``.collections()``, ``.aql.execute(query, bind_vars=...)``,
        and (optionally) ``.name``. The analyzer needs the same
        surface; the heuristic fallback uses only what's listed.
    include_owl:
        When ``True``, asks the analyzer to materialise the OWL
        Turtle representation of the conceptual model. The heuristic
        fallback ignores this flag (its bundles never carry inline
        OWL — PRD §6.3.4 calls this out as a known gap, satisfied
        by ``/mapping/export-owl`` in Slice 7).
    strategy:
        One of ``"auto"`` (analyzer-first, heuristic fallback on
        ``ImportError``), ``"analyzer"`` (raise if missing), or
        ``"heuristic"`` (skip the analyzer entirely; useful for
        smoke tests and air-gapped deployments).
    force_refresh:
        Accepted for forward-compat with the route layer's caching
        wrapper — this function does not cache, so the flag is a
        no-op here. Documented so downstream callers can pass it
        through unchanged.
    graph_name:
        Optional ArangoDB named-graph scope. When set, the fully
        enriched bundle is down-selected to that graph's vertex/edge
        collections (see :func:`schema.graph_scope.scope_bundle_to_graph`)
        before return. ``None`` (default) means "all collections".
    now:
        Injectable clock for the bundle's ``acquisitionTimestamp``
        metadata. Tests pin it; production callers leave ``None``.

    Returns
    -------
    MappingBundle
        A new bundle with the conceptual schema, physical mapping,
        provenance metadata, and (optionally) inline OWL. Always
        post-processed by :func:`_apply_rpt_enrichment` so RPT
        collections show up regardless of which tier ran.

    Raises
    ------
    ValueError
        If *strategy* is not one of the documented values.
    AnalyzerNotInstalledError
        When ``strategy="analyzer"`` is explicitly requested but
        the optional extra is missing.
    """

    if strategy not in _VALID_STRATEGIES:
        raise ValueError(f"strategy must be one of {_VALID_STRATEGIES!r}, got {strategy!r}")

    when = now if now is not None else datetime.now(UTC)
    # `force_refresh` is accepted for signature compat with the
    # cache-wrapping orchestrator (PRD signature includes it). The
    # acquisition path itself is stateless so the flag does not
    # change behavior here — but we still log it at DEBUG so a
    # confused operator can see the request landed.
    if force_refresh:
        logger.debug(
            "acquire_mapping_bundle called with force_refresh=True; "
            "this layer does not cache — flag has no effect here"
        )

    bundle = _acquire_via_strategy(
        db,
        strategy=strategy,
        include_owl=include_owl,
        when=when,
    )
    bundle = _apply_rpt_enrichment(db, bundle, when=when)
    bundle = _apply_edge_endpoint_enrichment(db, bundle, when=when)
    bundle = _normalize_bundle_warnings(bundle)
    bundle = _stamp_acquisition_timestamp(bundle, when=when)
    # Named-graph down-select (no-op when graph_name is None). Applied
    # last so the scope sees the fully-enriched bundle (RPT, edge
    # endpoints, OWL) before filtering. See schema/graph_scope.py.
    if graph_name:
        from .graph_scope import scope_bundle_to_graph

        bundle = scope_bundle_to_graph(db, bundle, graph_name)
    return bundle


def analyzer_available() -> bool:
    """Return ``True`` iff ``schema_analyzer`` can be imported in
    the current process. Cheap probe — used by:

    * Slice 6's ``_require_analyzer_unless_opted_out`` startup guard.
    * The route layer's ``/schema/info`` capability report.
    * Tests that need to assert behavior under both installed and
      missing-extra conditions.
    """

    try:  # noqa: SIM105 — the explicit shape mirrors the lazy import
        # pattern used everywhere else in this module
        import schema_analyzer  # noqa: F401
    except ImportError:
        return False
    return True


def db_shape_fingerprint(db: Any) -> str | None:
    """Return the analyzer's live shape fingerprint for *db*, or
    ``None`` if the analyzer extra is not installed.

    Thin wrapper around
    :func:`schema_analyzer.fingerprint_physical_shape` that:

    * Excludes the L2 cache collection (PRD §6.3.3) so a freshly-
      written cache row does not invalidate the cache it just landed
      in. This is correctness, not optimization — without the
      exclusion the cache will perma-thrash.
    * Returns ``None`` rather than raising on missing analyzer, so
      the cache layer can degrade to bundle-side fingerprints
      without a try/except in every call site.
    """

    return _live_fingerprint(db, kind="shape")


def db_counts_fingerprint(db: Any) -> str | None:
    """Return the analyzer's live shape+counts fingerprint, or
    ``None`` when the analyzer is not installed.

    Same exclusion semantics as :func:`db_shape_fingerprint`.
    """

    return _live_fingerprint(db, kind="counts")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AnalyzerNotInstalledError(RuntimeError):
    """Raised by :func:`acquire_mapping_bundle` when ``strategy="analyzer"``
    is requested but the optional extra is missing.

    Carries the install hint as the message so a user-facing error
    response (Slice 7 routes) can surface it verbatim.
    """

    def __init__(self, *, install_hint: str = ANALYZER_INSTALL_HINT) -> None:
        super().__init__(f"arangodb-schema-analyzer is not installed; install it with: {install_hint}")
        self.install_hint = install_hint


# ---------------------------------------------------------------------------
# Strategy dispatch
# ---------------------------------------------------------------------------


def _acquire_via_strategy(
    db: Any,
    *,
    strategy: Strategy,
    include_owl: bool,
    when: datetime,
) -> MappingBundle:
    """Dispatch to the analyzer or heuristic path based on *strategy*."""

    if strategy == "analyzer":
        if not analyzer_available():
            raise AnalyzerNotInstalledError()
        return _acquire_via_analyzer(db, include_owl=include_owl)

    if strategy == "heuristic":
        return _acquire_via_heuristic(db, when=when)

    # strategy == "auto": analyzer first, heuristic fallback on ImportError.
    if analyzer_available():
        return _acquire_via_analyzer(db, include_owl=include_owl)
    logger.warning(
        "arangodb-schema-analyzer is not installed; falling back to the "
        "heuristic mapping path. Install with: %s",
        ANALYZER_INSTALL_HINT,
    )
    bundle = _acquire_via_heuristic(db, when=when)
    return _attach_warning(
        bundle,
        code=W_ANALYZER_NOT_INSTALLED,
        message=(
            "Mapping built by the heuristic fallback because the "
            "schema-analyzer extra is not installed. Hybrid schemas "
            "(LPG with multi-class collections) may be misclassified."
        ),
        install_hint=ANALYZER_INSTALL_HINT,
    )


# ---------------------------------------------------------------------------
# Analyzer path
# ---------------------------------------------------------------------------


# Client SDK each provider needs; OpenRouter speaks the OpenAI wire protocol
# so it rides the ``openai`` package.
_PROVIDER_SDK_MODULE: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "openrouter": "openai",
}

# The analyzer's bundled per-provider default model can lag the live API:
# its Anthropic default ``claude-3-5-sonnet-latest`` now 404s. Pin a
# current, verified id so the LLM path works out of the box; override per
# deployment with ``SCHEMA_ANALYZER_MODEL``. Only providers whose default
# we have verified are listed — others fall through to the analyzer's own
# default.
#
# NOTE: the analyzer (v0.9) hard-codes ``temperature`` on every request,
# which the Claude 5 family (Sonnet 5, Opus 4.8) rejects with a 400
# ("temperature is deprecated for this model"). ``claude-haiku-4-5`` is the
# current Anthropic model that still accepts that request shape, so it is
# the safe default until the analyzer stops sending ``temperature``. Track
# that upstream fix; once shipped, this can move to a Claude 5 model.
_DEFAULT_ANALYZER_MODEL: dict[str, str] = {
    "anthropic": "claude-haiku-4-5-20251001",
}


def _analyzer_timeout_ms() -> int:
    """Per-call LLM budget for the analyzer, in milliseconds.

    Overridable via ``SCHEMA_ANALYZER_TIMEOUT_MS``; defaults to 180s (the
    library default of 60s times out on large schemas, silently degrading
    to baseline). Garbage / non-positive values fall back to the default.
    """
    raw = os.getenv("SCHEMA_ANALYZER_TIMEOUT_MS", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 180_000
    return value if value > 0 else 180_000


def _provider_sdk_available(provider: str) -> bool:
    """True iff the client SDK the analyzer needs for *provider* can be
    imported. Uses :func:`importlib.util.find_spec` so we probe without
    paying the import cost or risking import side effects.
    """

    import importlib.util

    module = _PROVIDER_SDK_MODULE.get(provider)
    return bool(module and importlib.util.find_spec(module) is not None)


def _resolve_analyzer_provider() -> str | None:
    """Pick the LLM provider for the schema analyzer, or ``None`` for the
    deterministic baseline.

    With no provider, ``AgenticSchemaAnalyzer`` runs its no-LLM baseline
    inference, which misclassifies hybrid / LABEL-style collections — e.g.
    it treats a ``name`` column as a type discriminator and emits one OWL
    class per value instead of a single class. Naming a provider here is
    what lets the analyzer do the intelligent classification the PRD
    assumes is canonical (§6.3.2).

    Resolution mirrors the NL2SPARQL policy
    (:func:`arango_sparql.nl2sparql.client.get_default_client`) so both
    LLM-backed subsystems select the same provider from one environment:

    1. Explicit ``SCHEMA_ANALYZER_PROVIDER``, then the generic
       ``LLM_PROVIDER`` (shared with the NL pipeline).
    2. Otherwise infer from which API key is present, but only pick a
       provider whose client SDK is importable — selecting one whose key is
       set but whose SDK is absent would make the analyzer silently drop
       back to baseline, the exact failure this shim exists to prevent.
    3. ``None`` when nothing usable is configured — the analyzer then
       degrades to baseline, exactly as it did before this shim.

    The key itself is deliberately *not* read here: the analyzer resolves
    it from the provider's canonical env var, so passing only the provider
    name keeps key handling in one place.
    """

    provider = (os.getenv("SCHEMA_ANALYZER_PROVIDER") or os.getenv("LLM_PROVIDER") or "").strip().lower()
    if provider:
        if provider not in ("openai", "anthropic", "openrouter"):
            logger.warning(
                "Unknown schema-analyzer provider %r; using deterministic "
                "baseline. Set SCHEMA_ANALYZER_PROVIDER to "
                "openai/anthropic/openrouter.",
                provider,
            )
            return None
        # Explicit request is honoured as-is; if its SDK/key is missing the
        # analyzer logs and degrades to baseline itself.
        return provider

    for candidate, key_var in (
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openrouter", "OPENROUTER_API_KEY"),
    ):
        if os.getenv(key_var) and _provider_sdk_available(candidate):
            return candidate
    return None


def _acquire_via_analyzer(db: Any, *, include_owl: bool) -> MappingBundle:
    """Run :class:`schema_analyzer.AgenticSchemaAnalyzer` and reshape
    its output into a :class:`MappingBundle`.

    The analyzer returns an ``AnalysisResult`` whose three sub-fields
    (``conceptual_schema``, ``physical_mapping``, ``metadata``) are
    consumed by :func:`schema_analyzer.export_mapping` to produce the
    canonical wire dict that :func:`mapping_from_wire_dict` expects.
    Sister project ``arango-cypher-py`` follows the same pattern;
    keeping the call sequence identical means cross-repo navigation
    is trivial (AGENTS.md §"Mimic, don't invent").
    """

    try:
        from schema_analyzer import AgenticSchemaAnalyzer, export_mapping
        from schema_analyzer.owl_export import (
            export_conceptual_model_as_owl_turtle,
        )
    except ImportError as exc:  # pragma: no cover — caller pre-checks
        raise AnalyzerNotInstalledError() from exc

    # Pass an LLM provider so the analyzer runs its intelligent
    # classification instead of the deterministic baseline (which cannot
    # tell a single-class collection from a LABEL-discriminated one). The
    # analyzer reads the matching API key from the environment itself, and
    # re-checks provider+key internally — a missing key or provider error
    # degrades to baseline rather than raising, so this stays best-effort.
    provider = _resolve_analyzer_provider()
    model = os.getenv("SCHEMA_ANALYZER_MODEL") or (
        _DEFAULT_ANALYZER_MODEL.get(provider) if provider else None
    )
    if provider:
        logger.info(
            "schema-analyzer using LLM provider=%s%s",
            provider,
            f" model={model}" if model else "",
        )
    else:
        logger.info(
            "schema-analyzer running deterministic baseline (no LLM provider "
            "configured; set SCHEMA_ANALYZER_PROVIDER or LLM_PROVIDER to enable "
            "intelligent classification)"
        )
    analyzer = AgenticSchemaAnalyzer(llm_provider=provider, model=model)
    # The analyzer's per-call LLM budget defaults to 60s, which is not enough
    # for a large schema (a 50+ collection database can need 2-3 minutes for
    # the model to emit a full mapping) — the request times out and the whole
    # classification silently degrades to the deterministic baseline. Give it
    # a generous default and let deployments tune it; the result is cached by
    # the route layer, so this cost is paid once per schema, not per request.
    timeout_ms = _analyzer_timeout_ms()
    analysis_result = analyzer.analyze_physical_schema(db, timeout_ms=timeout_ms)

    analysis_dict = {
        "conceptualSchema": analysis_result.conceptual_schema,
        "physicalMapping": analysis_result.physical_mapping,
        "metadata": _coerce_metadata_to_dict(analysis_result.metadata),
    }

    # The analyzer's only documented export target today is "cypher";
    # the wire shape for SPARQL is identical (PRD §6.2 — both
    # adapters consume the same MappingBundle), so re-using the
    # cypher target is correct, not a workaround.
    export = export_mapping(analysis_dict, target="cypher")

    owl_turtle: str | None = None
    if include_owl:
        try:
            owl_turtle = export_conceptual_model_as_owl_turtle(analysis_dict)
        except Exception:
            # OWL export is best-effort — a bundle without OWL is
            # still useful (the planner reads conceptual+physical
            # directly). We log at WARNING so an operator sees it
            # in the request log without it cascading into a 500.
            logger.warning(
                "schema_analyzer OWL export failed; bundle will lack "
                "owl_turtle. The /mapping/export-owl route will still "
                "work via the local turtle synthesizer.",
                exc_info=True,
            )

    wire_dict = {
        "conceptualSchema": export.get("conceptualSchema", {}),
        "physicalMapping": export.get("physicalMapping", {}),
        "metadata": export.get("metadata", {}),
        "owl_turtle": owl_turtle,
        "source": {
            "kind": "analyzer",
            "notes": "Generated by arangodb-schema-analyzer baseline path",
        },
    }
    return mapping_from_wire_dict(wire_dict)


def _coerce_metadata_to_dict(metadata: Any) -> dict[str, Any]:
    """The analyzer's ``AnalysisResult.metadata`` is a pydantic model
    in v0.6+; older releases returned a plain dict. Handle both
    shapes so a future minor-version bump cannot regress us silently.
    """

    if isinstance(metadata, dict):
        return metadata
    dump = getattr(metadata, "model_dump", None)
    if callable(dump):
        return dump(by_alias=True)
    # Last-ditch: coerce via JSON-able fallback. Loses field aliasing
    # but keeps the bundle structurally valid.
    return dict(metadata) if metadata else {}


# ---------------------------------------------------------------------------
# Heuristic path
# ---------------------------------------------------------------------------


def _acquire_via_heuristic(db: Any, *, when: datetime) -> MappingBundle:
    """Delegate to Slice 4's :func:`build_heuristic_mapping`.

    Wrapped here (rather than re-exported directly) so future
    behavior — e.g. attaching extra warnings, post-filtering — has
    one obvious place to live without churning the detect module.
    """

    return build_heuristic_mapping(db, schema_type="auto", now=when)


# ---------------------------------------------------------------------------
# RPT enrichment (PRD §6.3.2 step 2)
# ---------------------------------------------------------------------------


def _apply_rpt_enrichment(db: Any, bundle: MappingBundle, *, when: datetime) -> MappingBundle:
    """Run the RPT detector over *db* and merge any RPT-classified
    collections into the bundle's physical mapping.

    Why this runs even when the analyzer produced the bundle: the
    analyzer (v0.6.1) classifies into PG / LPG only — it does not
    recognise the legacy Foxx ``_triples`` RPT layout. A bundle
    that has a ``_triples`` collection but no RPT entry will be
    silently routed through the LPG translator, which produces
    wrong (and confusing) AQL. Running detection over the analyzer's
    output costs one extra pass over the user collections and
    closes that gap deterministically.

    Conflict resolution: when the RPT detector and the underlying
    bundle disagree about a collection (e.g. analyzer mapped
    ``_triples`` to ``COLLECTION``), the RPT entry wins — RPT
    detection has higher specificity (it requires four matching
    column names) and any false-positive would have to be hand-
    crafted to look exactly like an RPT bucket.

    Defensive: any failure in the RPT pass is logged and swallowed
    — the original bundle is returned untouched. RPT enrichment is
    additive, not load-bearing.
    """

    try:
        rpt_results = detect_rpt_pattern(db)
    except Exception:
        logger.warning(
            "RPT detection pass failed; bundle returned without RPT "
            "enrichment. Legacy _triples layouts may be misrouted.",
            exc_info=True,
        )
        return bundle

    rpt_entries: dict[str, dict[str, Any]] = {}
    for collection_name, result in rpt_results.items():
        if not result.is_rpt:
            continue
        rpt_entries[collection_name] = {
            "style": "RPT",
            "triplesCollection": result.triples_collection or collection_name,
            "subjectColumn": result.subject_column,
            "predicateColumn": result.predicate_column,
            "objectUriColumn": result.object_uri_column,
            "objectValueColumn": result.object_value_column,
            # Keep the per-collection coverage on the bundle so the
            # /schema/info route can surface "why was this an RPT?"
            # without re-running the detector.
            "rptCoverage": round(result.coverage_ratio, 4),
        }

    if not rpt_entries:
        return bundle

    # Synthesize RPT object-property relationships with rdf:type-typed
    # endpoints (PRD §6.3.2 step 2 — cross-collection inference). The
    # entity overlay above only marks the triples bucket as RPT; this
    # pass is what connects an object property (e.g. ``AUTHORED``) to
    # its typed domain/range (``Person`` → ``Doc``) so the planner and
    # NL→SPARQL surface see relationships, not just an opaque store.
    # Additive: never clobbers a relationship an upstream producer
    # (analyzer / imported OWL) already declared.
    try:
        rpt_relationships = infer_rpt_object_property_relationships(db, rpt_results)
    except Exception:
        logger.warning(
            "RPT object-property relationship synthesis failed; bundle "
            "keeps its existing relationships. Endpoint typing skipped.",
            exc_info=True,
        )
        rpt_relationships = {}

    # Build a new physical mapping with the RPT entries overlaid.
    # Preserves dict order: existing entries first, RPT-overridden
    # entries kept at their original position.
    new_physical = dict(bundle.physical_mapping)
    existing_entities = dict(new_physical.get("entities") or {})
    for name, spec in rpt_entries.items():
        existing_entities[name] = spec
    new_physical["entities"] = existing_entities

    if rpt_relationships:
        existing_relationships = dict(new_physical.get("relationships") or {})
        for name, spec in rpt_relationships.items():
            existing_relationships.setdefault(name, spec)
        new_physical["relationships"] = existing_relationships

    # Tag the bundle metadata so downstream consumers know RPT
    # enrichment ran. The cumulative pattern list is sorted to keep
    # serialisation deterministic for fingerprinting.
    new_metadata = dict(bundle.metadata)
    detected = list(new_metadata.get("detectedPatterns") or [])
    if "rpt" not in detected:
        detected.append("rpt")
    detected.sort()
    new_metadata["detectedPatterns"] = detected
    enrichment_log = list(new_metadata.get("enrichmentApplied") or [])
    entry: dict[str, Any] = {
        "kind": "rpt_overlay",
        "appliedAt": when.isoformat(),
        "collections": sorted(rpt_entries.keys()),
    }
    if rpt_relationships:
        entry["relationships"] = sorted(rpt_relationships.keys())
    enrichment_log.append(entry)
    new_metadata["enrichmentApplied"] = enrichment_log

    return MappingBundle(
        conceptual_schema=bundle.conceptual_schema,
        physical_mapping=new_physical,
        metadata=new_metadata,
        owl_turtle=bundle.owl_turtle,
        source=bundle.source,
    )


# ---------------------------------------------------------------------------
# Edge-endpoint enrichment (producer-agnostic, PRD §6.3.2 step 2)
# ---------------------------------------------------------------------------


def _apply_edge_endpoint_enrichment(db: Any, bundle: MappingBundle, *, when: datetime) -> MappingBundle:
    """Fill ``fromEntity`` / ``toEntity`` on edge relationships that are
    still ``"Any"`` (or absent), using ``_from`` / ``_to`` sampling.

    Why this runs over *any* bundle, analyzer-produced included: the
    analyzer classifies relationship *styles* (``DEDICATED_COLLECTION`` /
    ``GENERIC_WITH_TYPE``) but may leave the endpoints unresolved for the
    legacy and hybrid shapes this service targets. Re-using the same
    cross-collection inference the heuristic path runs
    (:func:`infer_edge_endpoints_from_db`) closes that gap regardless of
    which tier produced the bundle — exactly mirroring why RPT enrichment
    is always-on.

    **Strictly additive.** An endpoint the producer already pinned to a
    real entity is never overwritten; only ``"Any"`` / missing values are
    filled, and only when the inference resolves to a single entity. So a
    better upstream answer always wins, and an ambiguous edge stays
    ``"Any"`` rather than being replaced by a guess.

    Relationship-to-edge matching is by ``edgeCollectionName`` plus
    ``typeValue`` (the discriminator distinguishes the several
    ``GENERIC_WITH_TYPE`` relationships that share one edge collection).
    ``RPT_EDGE`` relationships carry no edge collection and are skipped
    here — their endpoints come from the RPT ``rdf:type`` synthesis pass.

    Defensive: any failure is logged and swallowed; the original bundle
    is returned untouched. Endpoint enrichment is additive, not
    load-bearing.
    """

    relationships = bundle.physical_mapping.get("relationships")
    if not isinstance(relationships, dict) or not relationships:
        return bundle

    # Only do the (one classification pass) work if there's actually an
    # unresolved edge endpoint to fill — keeps the analyzer happy-path
    # and the already-resolved heuristic path from paying for a no-op.
    def _needs_fill(spec: Any) -> bool:
        if not isinstance(spec, dict):
            return False
        if spec.get("style") == "RPT_EDGE" or not spec.get("edgeCollectionName"):
            return False
        return spec.get("fromEntity", "Any") == "Any" or spec.get("toEntity", "Any") == "Any"

    if not any(_needs_fill(spec) for spec in relationships.values()):
        return bundle

    try:
        endpoint_index = infer_edge_endpoints_from_db(db)
    except Exception:
        logger.warning(
            "Edge-endpoint enrichment failed; bundle returned without "
            "endpoint inference. Relationship fromEntity/toEntity may "
            "stay 'Any'.",
            exc_info=True,
        )
        return bundle

    if not endpoint_index:
        return bundle

    new_relationships: dict[str, Any] = {}
    filled: list[str] = []
    for name, spec in relationships.items():
        if not _needs_fill(spec):
            new_relationships[name] = spec
            continue
        edge_collection = spec["edgeCollectionName"]
        type_value = spec.get("typeValue")  # None for DEDICATED_COLLECTION
        inferred = endpoint_index.get(edge_collection, {}).get(type_value)
        if inferred is None:
            new_relationships[name] = spec
            continue
        from_entity, to_entity = inferred
        updated = dict(spec)
        changed = False
        if updated.get("fromEntity", "Any") == "Any" and from_entity != "Any":
            updated["fromEntity"] = from_entity
            changed = True
        if updated.get("toEntity", "Any") == "Any" and to_entity != "Any":
            updated["toEntity"] = to_entity
            changed = True
        new_relationships[name] = updated
        if changed:
            filled.append(name)

    if not filled:
        return bundle

    new_physical = dict(bundle.physical_mapping)
    new_physical["relationships"] = new_relationships

    new_metadata = dict(bundle.metadata)
    enrichment_log = list(new_metadata.get("enrichmentApplied") or [])
    enrichment_log.append(
        {
            "kind": "edge_endpoint_inference",
            "appliedAt": when.isoformat(),
            "relationships": sorted(filled),
        }
    )
    new_metadata["enrichmentApplied"] = enrichment_log

    return MappingBundle(
        conceptual_schema=bundle.conceptual_schema,
        physical_mapping=new_physical,
        metadata=new_metadata,
        owl_turtle=bundle.owl_turtle,
        source=bundle.source,
    )


# ---------------------------------------------------------------------------
# Metadata / warning helpers
# ---------------------------------------------------------------------------


def _attach_warning(
    bundle: MappingBundle,
    *,
    code: str,
    message: str,
    install_hint: str | None = None,
) -> MappingBundle:
    """Return a copy of *bundle* with a structured warning appended
    to ``metadata.warnings``. Mirrors the sister project's
    :func:`_attach_warning`; documented at PRD §6.3.4 (warning
    catalogue) and §6.4 (route surfaces).
    """

    new_metadata = dict(bundle.metadata)
    warnings = list(new_metadata.get("warnings") or [])
    entry: dict[str, Any] = {"code": code, "message": message}
    if install_hint:
        entry["install_hint"] = install_hint
    warnings.append(entry)
    new_metadata["warnings"] = warnings
    return MappingBundle(
        conceptual_schema=bundle.conceptual_schema,
        physical_mapping=bundle.physical_mapping,
        metadata=new_metadata,
        owl_turtle=bundle.owl_turtle,
        source=bundle.source,
    )


def _normalize_warning_entry(entry: Any) -> dict[str, Any]:
    """Coerce one warning into the canonical ``{code, message}`` dict.

    Dicts pass through untouched (the catalogue producers already emit
    the right shape). A bare string is wrapped under
    :data:`W_ANALYZER_ADVISORY`; any other type is stringified so the
    wire shape stays ``dict[str, Any]`` no matter what an upstream
    producer hands us.
    """

    if isinstance(entry, dict):
        return entry
    return {"code": W_ANALYZER_ADVISORY, "message": str(entry)}


def _normalize_bundle_warnings(bundle: MappingBundle) -> MappingBundle:
    """Ensure ``metadata.warnings`` is a list of ``{code, message}`` dicts.

    The wire contract (:mod:`arango_sparql.service.models`) types every
    ``warnings`` field as ``list[dict]``; the analyzer, however, can attach
    free-text string advisories (e.g. the "LLM provider not configured"
    baseline-inference note). Left unconverted those strings fail the
    response-model validation and surface as an opaque 500 on
    ``/schema/introspect`` and ``/schema/force-reacquire``. Normalising
    here — at the single point every bundle flows through — restores the
    invariant for *all* consumers (routes, planner, NL pipeline).

    Returns *bundle* unchanged when there is nothing to fix (no warnings,
    or all already dicts) so the common path allocates nothing.
    """

    raw = (bundle.metadata or {}).get("warnings")
    if not isinstance(raw, list) or all(isinstance(w, dict) for w in raw):
        return bundle

    new_metadata = dict(bundle.metadata)
    new_metadata["warnings"] = [_normalize_warning_entry(w) for w in raw]
    return MappingBundle(
        conceptual_schema=bundle.conceptual_schema,
        physical_mapping=bundle.physical_mapping,
        metadata=new_metadata,
        owl_turtle=bundle.owl_turtle,
        source=bundle.source,
    )


def _stamp_acquisition_timestamp(bundle: MappingBundle, *, when: datetime) -> MappingBundle:
    """Stamp ``metadata.acquisitionTimestamp`` so cache layers and
    the ``/schema/info`` route can surface "when did we last
    acquire?" without consulting an external clock.

    Idempotent: an existing timestamp is preserved (heuristic
    bundles already stamp their own — :func:`build_heuristic_mapping`
    sets ``metadata.acquiredAt``). We only fill the gap for
    analyzer bundles, whose metadata schema does not include this
    field today.
    """

    new_metadata = dict(bundle.metadata)
    if "acquisitionTimestamp" not in new_metadata:
        new_metadata["acquisitionTimestamp"] = when.isoformat()
    if bundle.source is None:
        new_source: MappingSource | None = None
    else:
        new_source = bundle.source
    return MappingBundle(
        conceptual_schema=bundle.conceptual_schema,
        physical_mapping=bundle.physical_mapping,
        metadata=new_metadata,
        owl_turtle=bundle.owl_turtle,
        source=new_source,
    )


# ---------------------------------------------------------------------------
# Live-DB fingerprint helpers
# ---------------------------------------------------------------------------


def _live_fingerprint(db: Any, *, kind: Literal["shape", "counts"]) -> str | None:
    """Common implementation behind :func:`db_shape_fingerprint` and
    :func:`db_counts_fingerprint`. Returns ``None`` on missing
    analyzer or unexpected error so the cache layer never has to
    deal with exceptions from this code path.
    """

    try:
        from arango_sparql.schema.cache import L2_COLLECTION_NAME

        if kind == "shape":
            from schema_analyzer import fingerprint_physical_shape as fn
        else:
            from schema_analyzer import fingerprint_physical_counts as fn
    except ImportError:
        return None

    try:
        return fn(db, exclude_collections={L2_COLLECTION_NAME})
    except TypeError:
        # Older analyzer releases (< 0.5) did not accept
        # exclude_collections. Re-try without it; the cache row will
        # then count toward the fingerprint, but the cache is still
        # functionally correct (it just refreshes one extra time
        # after each write).
        try:
            return fn(db)
        except Exception:
            logger.warning(
                "Live DB fingerprint (%s) failed; cache will fall back to bundle-side fingerprints.",
                kind,
                exc_info=True,
            )
            return None
    except Exception:
        logger.warning(
            "Live DB fingerprint (%s) failed; cache will fall back to bundle-side fingerprints.",
            kind,
            exc_info=True,
        )
        return None


__all__ = [
    "ANALYZER_INSTALL_HINT",
    "ANALYZER_VERSION_RANGE",
    "W_ANALYZER_NOT_INSTALLED",
    "W_SCHEMA_HEURISTIC_FALLBACK",
    "AnalyzerNotInstalledError",
    "Strategy",
    "acquire_mapping_bundle",
    "analyzer_available",
    "db_counts_fingerprint",
    "db_shape_fingerprint",
]
