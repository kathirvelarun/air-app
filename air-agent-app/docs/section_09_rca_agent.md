# The RCA Service: LLM Investigation Agent

This covers `POST /api/v1/rca` — the LLM-based root-cause reasoning layer
described in `reference/AIR-Investigation.pdf` ("LLM Integration - Direct
Evidence Collection Handoff", v2.0). It implements the guide's **Section 9**
(Handoff to RCA): the first place in this codebase an LLM produces Key
Findings, a Root Cause Analysis, and a Suggestion Plan from evidence —
every earlier stage (Sections 1, 3-8) is purely deterministic.

See `docs/requests/section_09_rca_request.json` for a sample request body
(a real `/api/v1/investigate` response, captured verbatim), and
`docs/section_08_investigate_service.md` for how the evidence it consumes
is produced.

## 1. Architecture: Direct Evidence Collection Handoff

`reference/AIR-Investigation.pdf` makes one architectural decision
explicit up front: **there is no separate `EvidenceValidator` stage.**
Whatever `POST /api/v1/investigate` returns is, by construction, "accepted"
for the LLM call — Pydantic validating the request body *is* the
acceptance check. Nothing re-scores or re-judges evidence quality before
handing it to the model.

```text
EvidenceCollection Function
  |
  | consolidated evidence payload (InvestigateResponse)
  v
LLM Investigation Call  (POST /api/v1/rca)
  |
  v
Structured InvestigationResult
  |
  +--> Key Findings
  +--> RCA
  +--> Suggestion Plan
  +--> Confidence / Source References
```

Concretely, `POST /api/v1/rca`'s request body is typed as
`InvestigateResponse` — the *exact same model* `/api/v1/investigate`
returns (`src/air_agent_app/models/investigate.py`). No transformation
happens in between; a caller can pipe one endpoint's response straight
into the other's request body. `tests/test_rca_api.py`'s
`test_rca_accepts_the_exact_investigate_response_body` proves this by
doing exactly that.

| Layer | Responsibility | LLM? |
| --- | --- | --- |
| EvidenceCollection (`/api/v1/investigate`) | Collect, normalize, aggregate evidence | No |
| Request parsing (`InvestigateResponse` validation) | Ensure the payload matches the declared schema | No |
| LLM Investigation (`RcaService`) | Interpret the evidence, produce Key Findings, RCA, Suggestions | Yes |
| Post-LLM checks (`rca_post_checks.py`) | Validate output schema and source references | No |

## 2. Source reference strategy

The evidence payload carries no per-item ID — no `log-001`, no
`metric-001`. If the model needs to cite *which* evidence backs a finding,
it must use a reference this codebase derives deterministically, never one
it invents (`investigation/rca_source_refs.py`):

```python
def evidence_ref(item: Evidence) -> str:
    return f"{item.agent_name}/{item.evidence_type}"

# LogsAgent/LOG, MetricsAgent/METRIC, TracesAgent/TRACE, DeploymentAgent/DEPLOYMENT
```

`build_source_reference_map(response)` builds the full `{reference:
metadata}` map sent to the model alongside the evidence, and the exact
same map is used afterward to reject anything the model cites that isn't
in it (`rca_post_checks.py::validate_source_refs`).

## 3. The system prompt (`context/prompts/rca.py`)

Kept in its own module, isolated from workflow code, and versioned
independently (`PROMPT_VERSION = "1.0"`) — mirroring
`context/prompts/planner.py`'s pattern for Section 1. It is copied from
the PDF's own "Clean LLM System Prompt" section, rewrapped only for the
100-column line limit (no wording changed). It states, explicitly:

- What the model may use: only the evidence, timeline, summaries,
  findings, and metadata in the supplied request.
- What it must never do: call or assume access to ELF, Prometheus,
  Jaeger, or GitHub; invent evidence, timestamps, config values, or
  source references; treat temporal correlation as proof of causation;
  describe a `HEALTHY`-classified metric as resource exhaustion.
- When to give up: if the evidence can't support a defensible root cause,
  return `investigation_status = "INCONCLUSIVE"` rather than fabricate one.
- Confidence guidance banding 0.90-1.00 down to "below 0.50 means
  INCONCLUSIVE, not a low-confidence guess."

Evidence from the current investigation never goes in this file — it goes
in the user message, built per-request by `context/rca_prompt_builder.py`
from the live evidence payload and source-reference map (both inserted as
JSON *values*, never string-concatenated, so evidence content can never be
mistaken for template syntax).

## 4. Why the model boundary takes typed objects, not a rendered prompt

Section 1's `PlannerService` takes an already-rendered `ChatPromptValue`
as its model boundary, and its offline test double
(`OfflinePlanModel`) simply ignores prompt content — `PlannerOutput` has
no field that must trace back to specific input data.

`InvestigationResult` is different: every `source_refs` list is
re-validated against the evidence actually supplied. A test double for
RCA needs real access to *which* evidence and references it's allowed to
cite, or it cannot produce a fixture that survives `validate_source_refs`
for an arbitrary subset of agents. So the boundary here
(`RcaLLMClient` in `investigation/rca_service.py`) is typed:

```python
class RcaLLMClient(Protocol):
    def generate(
        self, evidence: InvestigateResponse, source_reference_map: dict[str, dict[str, str]]
    ) -> InvestigationResult: ...
```

Only the *live* implementation (`tools/llm/rca_llm_service.py::RcaLLMService`)
ever converts this into a rendered prompt internally, via
`RcaPromptBuilder`. The offline fixture
(`tools/mock/fixtures/offline_investigation_model.py::OfflineInvestigationModel`)
works with the typed evidence directly — grounding every finding, the RCA,
and its one suggestion in evidence items that actually cleared the
"found something" confidence tier (`>= 0.9`, the same tier every evidence
agent already uses), so the fixture is valid for any evidence subset a
test constructs, not just the full four-agent payment-service scenario.

## 5. Post-LLM checks (`investigation/rca_post_checks.py`)

Two checks run after every model call — **output-contract** checks, not a
revival of `EvidenceValidator`:

- **`validate_source_refs`**: collects every `source_refs` list across
  `key_findings`, `rca`, and each suggested action, plus
  `source_refs_used`, and rejects the result if anything in that set isn't
  a key in the source-reference map the model was given. This is what
  actually enforces "never invent evidence IDs or source references" —
  the system prompt states the rule, this check verifies it held.
- **`enforce_human_approval`**: forces `requires_human_approval = True` on
  any suggested action whose text matches a production-change term
  (`rollback`, `redeploy`, `restart`, `scale`, `change config`, `disable`,
  `enable`, `route traffic`, ...) regardless of what the model itself set
  the flag to. The model is given this same rule (system prompt rule 12),
  but it is never trusted alone for production-impacting actions. Since
  every model here is frozen (`extra="forbid", frozen=True`, matching the
  rest of this codebase), a changed suggestion means a new object via
  `model_copy`, never an in-place mutation.

`investigation_id` gets the same trust treatment: the schema includes it
(matching the PDF), but `RcaService.investigate()` always overwrites
whatever the model returned with the trusted value from the evidence
payload before returning. Never trust a model to echo a UUID back
correctly.

## 6. Bounded retry (`investigation/rca_retry.py`)

```python
MAX_RCA_ATTEMPTS = 2
```

An invalid structured output, a transport/provider failure, or an
invented source reference surviving `validate_source_refs` are all
**execution problems** worth one bounded retry of the same accepted
evidence payload. `INCONCLUSIVE` is never one of these — it's a valid
semantic outcome and is never retried. After `MAX_RCA_ATTEMPTS` failures,
`run_with_retry` raises one `RcaExecutionError` (chaining the last
underlying error), which the API layer maps to `502` — see
`api/error_handlers.py::rca_execution_error_handler`. A schema-parse
failure on the *request* itself never reaches the model at all; that's a
`422` from Pydantic validation, not an `RcaExecutionError`.

## 7. Investigation outcomes

| Status | Meaning | HTTP |
| --- | --- | --- |
| `COMPLETED` | The model produced defensible findings and an RCA from the accepted evidence. | `200` |
| `INCONCLUSIVE` | The model cannot establish a defensible root cause from the supplied evidence. | `200` — not an error |
| execution failure (exhausted retries) | Provider timeout, malformed structured output, or persistent invented references. | `502` |

## 8. Response sent

```json
{
  "investigation_id": "...",
  "investigation_status": "COMPLETED",
  "key_findings": [ { "finding_id": "KF-001", "finding": "...", "source_refs": ["LogsAgent/LOG"], "confidence": 0.9 } ],
  "rca": { "root_cause": "...", "contributing_factors": [...], "source_refs": [...], "confidence": 0.9, "uncertainty": "..." },
  "suggestion_plan": {
    "immediate_actions": [ { "suggestion_id": "SG-001", "action": "...", "rationale": "...", "priority": "HIGH", "risk": "LOW", "requires_human_approval": false, "source_refs": [...] } ],
    "verification_steps": ["..."],
    "rollback_plan": [],
    "follow_up_actions": []
  },
  "overall_confidence": 0.9,
  "source_refs_used": ["LogsAgent/LOG", "MetricsAgent/METRIC", "TracesAgent/TRACE", "DeploymentAgent/DEPLOYMENT"],
  "missing_information": []
}
```

Confirmed against the live OpenAPI schema and an actual response body via
the offline fixture chained straight off a real `/api/v1/investigate`
call — both list exactly `investigation_id, investigation_status,
key_findings, rca, suggestion_plan, overall_confidence, source_refs_used,
missing_information`. No `key_findings`/`rca` naming collision with
`/api/v1/investigate`'s own response: that endpoint's schema has neither
field (see `docs/section_08_investigate_service.md`).

## 9. On EvidenceValidator

`reference/AIR-Investigation.pdf` states this directly: **EvidenceValidator
is removed from this flow.** There is no semantic evidence-quality gate,
no `SUFFICIENT`/`NEEDS_MORE_EVIDENCE` routing, and no quality score
anywhere in this codebase's evidence-to-RCA path. "Removing EvidenceValidator
does not mean accepting malformed JSON" — Pydantic still parses and rejects
transport/schema errors at every boundary (`InvestigateResponse` on the way
in, `InvestigationResult` on the way out); what's absent is a *second*,
separate semantic judgment of whether the evidence is "good enough" before
the LLM ever sees it. That judgment is now entirely the LLM's job
(`INCONCLUSIVE` is how it's expressed), backed only by the deterministic
post-LLM checks in section 5 above.
