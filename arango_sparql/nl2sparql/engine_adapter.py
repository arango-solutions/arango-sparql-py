"""Adapter seams that plug ``arango_sparql`` into the shared NL engine.

The language-agnostic :class:`arango_query_core.nl.engine.NLQueryEngine`
owns the generate → validate → repair *flow* and token accounting, but it
cannot know anything SPARQL-specific or anything about *this* service's
audit/cost bookkeeping. Those concerns live here, as two small pieces the
pipeline injects into the engine:

* :class:`EngineProviderBridge` — adapts our
  :class:`~arango_sparql.nl2sparql.client.LLMClient`
  (``generate(messages) -> LLMResponse``) to the engine's
  :class:`~arango_query_core.nl.providers.LLMProvider` protocol
  (``generate(system, user) -> (content, usage_dict)``). It also owns the
  per-call :class:`~arango_sparql.nl2sparql.models.LLMCallRecord` audit
  trail (RESEARCH work-item 3, option (b): the bridge records one record
  per provider call, since the engine's ``NLResult`` only carries token
  *totals*, not per-call provider/model/cost).

* :class:`SparqlAdapter` — implements the five
  :class:`~arango_query_core.nl.seams.QueryLanguageAdapter` seams, each
  mapped onto a shipped ``nl2sparql`` / transpiler piece. Its ``validate``
  seam runs against the resolver **injected into the constructor** (the
  pipeline's own ``self.resolver``), never a resolver rebuilt from
  ``ontology_ttl`` — so a mapping-JSON / analyzer-enriched request (where
  ``ontology_ttl`` is ``""`` but the resolver is populated) validates
  against the same schema the pipeline's final re-translate will use.

The pipeline (see :mod:`arango_sparql.nl2sparql.pipeline`) wires these two
into ``NLQueryEngine`` in Wave 3; isolating them here lets the
verdict-reproduction, record-accounting, and resolver-parity invariants be
proven independently of the pipeline re-point.
"""

from __future__ import annotations

import time
from pathlib import Path

from arango_query_core.nl import FewShotIndex, cached_few_shot_index
from arango_query_core.nl.grounding import LabelIndex
from arango_query_core.nl.seams import GuardrailVerdict, ValidationResult

from ..api import translate as _api_translate
from ..errors import SparqlError, UnsupportedSparqlError
from ..translate.resolver import SchemaResolver
from .client import LLMClient
from .cost import estimate_llm_cost_usd
from .models import LLMCallRecord, LLMResponse
from .prompt import PromptBuilder, extract_sparql_from_response
from .repair import format_repair_context

# The four usage keys the engine's LLMProvider protocol expects in the
# returned usage dict — kept in sync with ``arango_query_core.nl.engine._USAGE_KEYS``.
_USAGE_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens")

# Curated few-shot bank (07-02) — disjoint from tests/nl2sparql/eval/corpus.yml.
# parents[2] = repo root: engine_adapter.py -> nl2sparql -> arango_sparql -> repo.
_FEWSHOT_BANK_PATH = Path(__file__).resolve().parents[2] / "tests" / "nl2sparql" / "eval" / "fewshot_bank.yml"


class EngineProviderBridge:
    """Adapt an :class:`LLMClient` to the engine's ``LLMProvider`` protocol.

    The engine calls :meth:`generate` with pre-rendered ``system`` / ``user``
    strings and expects ``(content, usage_dict)`` back. This bridge turns that
    into the ``[{role, content}, …]`` message list our clients consume, and —
    critically — records one :class:`LLMCallRecord` per call on :attr:`records`
    so the pipeline can reconstruct the exact audit trail the engine's
    ``NLResult`` token totals alone cannot express (provider, model, per-call
    cost). This mirrors ``pipeline._call_llm_raw`` field-for-field.

    A transport / provider exception is recorded as an error record (with
    ``cost_usd == 0.0``) and then **re-raised**, so the engine loop terminates
    on a real transport failure rather than validating an empty string and
    burning its retry budget.

    The returned ``content`` is the completion run through
    :func:`extract_sparql_from_response` — the same robust extractor the
    standalone pipeline used. The engine then applies its own
    ``_strip_code_fence`` to that text, but since already-extracted SPARQL is
    fence-free that call is a no-op. Doing extraction here (rather than relying
    on the engine's stricter, prefix-sensitive stripper) preserves the
    standalone pipeline's extraction semantics exactly, so a completion with
    leading prose (``"Here you go:\\n\\n```sparql…"``) is handled identically.
    """

    def __init__(self, client: LLMClient) -> None:
        self._client = client
        self.records: list[LLMCallRecord] = []

    def generate(self, system: str, user: str) -> tuple[str, dict[str, int]]:
        provider = getattr(self._client, "provider", "unknown")
        model = getattr(self._client, "model", "unknown")
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        t0 = time.perf_counter()
        try:
            response: LLMResponse = self._client.generate(messages)
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            self.records.append(
                LLMCallRecord(
                    provider=provider,
                    model=model,
                    sparql="",
                    cost_usd=0.0,
                    latency_ms=elapsed_ms,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            # Re-raise so the engine loop stops on a genuine transport failure
            # instead of retrying against an empty candidate.
            raise
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        cost = estimate_llm_cost_usd(provider, model, response.prompt_tokens, response.completion_tokens)
        self.records.append(
            LLMCallRecord(
                provider=provider,
                model=model,
                sparql="",
                cost_usd=cost,
                latency_ms=elapsed_ms,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                cached_tokens=response.cached_tokens,
            )
        )
        return extract_sparql_from_response(response.content), {
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
            "cached_tokens": response.cached_tokens,
        }


class SparqlAdapter:
    """The five ``QueryLanguageAdapter`` seams for SPARQL.

    Each seam maps onto a shipped ``nl2sparql`` / transpiler piece:

    ==========================  ============================================
    Seam                        Maps to
    ==========================  ============================================
    ``grammar_prompt_section``  :class:`PromptBuilder`'s system turn
    ``few_shot_index``          populated ``FewShotIndex`` via
                                 ``cached_few_shot_index`` (mode=auto)
    ``validate``                :func:`arango_sparql.api.translate`
    ``repair_hint``             :func:`format_repair_context`
    ``guardrails``              allow-all (no tenant/write-op checks yet)
    ``grounding_index``         injected ``LabelIndex`` (explicit-injection
                                 only this phase — no production default)
    ==========================  ============================================

    The constructor takes the caller's **already-built** ``resolver`` (in
    production the pipeline's ``self.resolver``) and a SEPARATE ``ontology_ttl``
    used ONLY to embed the Turtle text into the prompt. The two are decoupled
    on purpose: a mapping-JSON / analyzer-enriched request populates the
    resolver while leaving ``ontology_ttl`` empty. Rebuilding a resolver from
    ``ontology_ttl`` inside :meth:`validate` would drive the engine's
    accept/reject loop against the WRONG (empty) schema and diverge from the
    pipeline's final re-translate.
    """

    language = "sparql"

    def __init__(
        self,
        *,
        resolver: SchemaResolver,
        ontology_ttl: str = "",
        few_shot_index: FewShotIndex | None = None,
        few_shot_mode: str = "auto",
        grounding_index: LabelIndex | None = None,
    ) -> None:
        self.resolver = resolver
        self.ontology_ttl = ontology_ttl
        self._few_shot_index = few_shot_index
        self._few_shot_mode = few_shot_mode
        self._grounding_index = grounding_index

    def grammar_prompt_section(self, schema_context: str) -> str:  # seam 1
        # Reuse the shipped system-prompt template so the grammar + ontology
        # block stays byte-aligned with the standalone PromptBuilder.
        return PromptBuilder(ontology_ttl=self.ontology_ttl).render_system()

    def few_shot_index(self) -> FewShotIndex | None:  # seam 2
        # Explicit injection wins (tests / the Plan 04 sweep); otherwise return
        # the memoized, populated index built from the curated bank (07-02) via
        # the shared engine's module-scope cached_few_shot_index factory — never
        # constructed inline here (Pitfall 1: a fresh FewShotIndex per adapter
        # construction would reload the SentenceTransformer model + re-embed the
        # whole bank on every request/eval case).
        #
        # WARNING: this PRODUCTION seam requests mode="auto" (D-05) — a
        # deployment lacking the `.[dense]` extra (no torch/sentence-transformers
        # installed) gracefully degrades to BM25, then to a no-op retriever,
        # rather than crashing. This means the measured NL-FEW-02 dense-mode
        # pass-rate lift applies in production ONLY when the service is
        # installed with `.[dense]` (`pip install '.[dense]'`); a default
        # `.[nl]`-only install silently runs BM25/no-op, not dense. Plan 04's
        # eval sweep therefore reports the bm25 arm as the honest DEFAULT-INSTALL
        # number and scopes the dense-lift headline to `.[dense]` deployments.
        if self._few_shot_index is not None:
            return self._few_shot_index
        return cached_few_shot_index(str(_FEWSHOT_BANK_PATH), self._few_shot_mode)

    def validate(self, query: str) -> ValidationResult:  # seam 3
        # Validate against the INJECTED resolver — the same schema the
        # pipeline's final re-translate uses — never one rebuilt from
        # ``ontology_ttl`` (which may be empty for mapping-JSON requests).
        try:
            _api_translate(query, resolver=self.resolver)
            return ValidationResult(ok=True)
        except SparqlError as exc:
            return ValidationResult(ok=False, error=str(exc), code=getattr(exc, "code", ""))

    def repair_hint(self, query: str, failure: ValidationResult) -> str:  # seam 4
        # Reproduce ``format_repair_context`` output. The engine hands us a
        # ValidationResult (code + error), not a SparqlError, so reconstruct
        # the matching error type — this preserves the exact ``[CODE] msg`` +
        # SPARQL-1.1 hint wording the repair-loop tests assert on.
        if failure.code == UnsupportedSparqlError.code:
            error: SparqlError = UnsupportedSparqlError(failure.error)
        else:
            error = SparqlError(failure.error, code=failure.code or SparqlError.code)
        return format_repair_context(error)

    def guardrails(self, query: str, context: dict) -> GuardrailVerdict:  # seam 5
        # Allow-all — no tenant/write-op checks this phase.
        return GuardrailVerdict(allowed=True)

    def grounding_index(self) -> LabelIndex | None:  # seam 6
        # Explicit injection only this phase — no cached-default fallback
        # exists yet (unlike few_shot_index's cached_few_shot_index branch):
        # there is no canonical, production-owned source of instance/entity
        # label data the way there is a curated few-shot bank (RESEARCH Open
        # Question 2). A deployment that never injects a LabelIndex runs
        # ungrounded (grounding_index() -> None), which the engine treats
        # identically to seam 2's "no index" case.
        return self._grounding_index

    def grounding_prompt_section(self, question: str, index: LabelIndex, k: int = 20) -> str:  # seam 6 (renderer)
        # Verbatim wording from the spike's entity_block
        # (scratchpad/nl-grounding-spike/grounding_spike.py::entity_block) —
        # this exact header + instruction text is what was empirically
        # measured to lift CK25 execution-graded accuracy 12.2% -> 24.5%
        # (McNemar p=0.031). Do NOT paraphrase; rephrasing invalidates the
        # measured lift. The retrieval/rendering machinery (sanitization,
        # ranking, "no matches -> empty string") lives in LabelIndex
        # (Plan 01) — this method only supplies the fixed SPARQL-specific
        # header/instruction/id_prefix/id_suffix constants.
        return index.format_prompt_section(
            question,
            k=k,
            header="## Known entities (use these EXACT IRIs)",
            instruction=(
                "The question may refer to specific named individuals/things below. When it "
                "does, use the entity's EXACT IRI directly in your query (e.g. `<IRI> pv:... ?x`) "
                "instead of matching on a name literal. Not all listed entities are relevant."
            ),
            id_prefix="<",
            id_suffix=">",
        )
