# Agent Proposal Gateway Live Smoke v0

This runbook is for a manual local smoke against an OpenAI-compatible server
such as LM Studio, Ollama with an OpenAI-compatible endpoint, or another local
server.

It is not a product CLI, a model benchmark, or a proof that the model reasoned
correctly. The live provider is an untrusted proposer. DSM composes context,
validates the proposal shape and honesty boundaries, assigns status, and writes
an Agent Memory audit.

Every successful run prints:

```text
validated for form/honesty, not truth
```

## 1. Start a Local Server

For LM Studio:

1. Open LM Studio.
2. Load a chat model.
3. Start the local OpenAI-compatible server.
4. Confirm the base URL, usually:

```text
http://localhost:1234/v1
```

For Ollama or another local server, use its OpenAI-compatible base URL.

## 2. Choose a Model

Use the model name exposed by the local server. If unsure, inspect the server
UI or API. The default `local-model` is only a placeholder.

## 3. Run the Smoke

Before calling a live provider, inspect the exact provider-facing contract and
OpenAI-compatible payload:

```bash
./.venv312/bin/python tools/agent_proposal_gateway_v0/live_smoke.py \
  --dry-run-contract \
  --base-url http://localhost:1234/v1 \
  --provider-name lmstudio \
  --model local-model
```

The dry-run does not call a provider and does not write audit data. It prints the
DSM-composed context plus the prompt payload. The contract tells the provider:

- surface each `required_check`;
- fill `claimed_checks` only for checks substantively covered;
- include model-written coverage for each claimed check;
- include `limitations`;
- do not assign status;
- do not claim truth;
- do not auto-promote candidate rules;
- DSM validates form/honesty, not truth.

The dry-run is an inspection aid only. It does not prove live acceptance.

Run from the repository root:

```bash
./.venv312/bin/python tools/agent_proposal_gateway_v0/live_smoke.py \
  --live \
  --base-url http://localhost:1234/v1 \
  --provider-name lmstudio \
  --model local-model \
  --data-dir .venv-live-smoke/agent-proposal
```

Run this from the repository root. The script bootstraps repository imports when
executed by path, so manual `PYTHONPATH=.` is not required.

Useful options:

```bash
--temperature low
--timeout 30
--max-tokens 700
--user-id mohamed
--domain omari_ai
--skill-id omari_ai.lead_capture_reliability
```

Environment variables are also supported:

```text
AGENT_PROPOSAL_BASE_URL
AGENT_PROPOSAL_MODEL
AGENT_PROPOSAL_TEMPERATURE
AGENT_PROPOSAL_TIMEOUT
AGENT_PROPOSAL_MAX_TOKENS
AGENT_PROPOSAL_PROVIDER_NAME
AGENT_PROPOSAL_DATA_DIR
AGENT_PROPOSAL_USER_ID
AGENT_PROPOSAL_DOMAIN
AGENT_PROPOSAL_SKILL_ID
```

## 4. Read the Status

The smoke prints:

- provider and model metadata;
- dogfood data directory;
- DSM validation status;
- Agent Memory decision hash;
- input context hash;
- raw output hash;
- explain JSON;
- Markdown audit report.

Only three statuses exist:

- `accepted_for_audit`
- `needs_human_review`
- `rejected_by_validator`

Interpretation:

- `accepted_for_audit`: admitted to the audit trail, not proven true.
- `needs_human_review`: persisted and explainable, but not retrieval-safe.
- `rejected_by_validator`: the validator did its job; the proposal remains
  auditable but must not contaminate retrieval.

If a live model over-promises truth or finality, `rejected_by_validator` is the
correct outcome.

## First Observed Live Smoke Result

The first observed LM Studio live smoke ran successfully against:

```text
nvidia/nemotron-3-nano-omni
```

DSM assigned:

```text
rejected_by_validator
```

This is a boundary success. A real provider proposal reached DSM, and DSM
rejected it because required checks were not covered or surfaced and limitations
were missing. This proves the reject path on live provider output.

It does not yet prove the `accepted_for_audit` live path.

The acceptability test proves the validator can accept a conformant proposal and
discriminate against missing required checks. It does not prove the live
`accepted_for_audit` path.

Observed labels only:

- warning: `missing_limitations`
- rejection: `required_check_not_covered_or_surfaced`
- affected checks:
  - `bug_before_feature`
  - `external_evidence_limit_disclosed`
  - `known_context_not_reasked`
  - `persistence_failure_checked`

Do not commit raw model output or dogfood artifacts from live smoke runs.

Open diagnostic question:

Required checks were present in the DSM context but were not covered or surfaced
by the model. Possible causes:

1. weak or small model;
2. context legibility issue;
3. detection strictness issue.

Investigate without lowering the validator bar.

## Offline Diagnosis Summary

Dogfood artifacts from the first LM Studio and Ollama live smokes were inspected
locally. Raw model output and dogfood artifacts are intentionally not committed.

Redacted classification:

| Check | LM Studio | Ollama |
| --- | --- | --- |
| `bug_before_feature` | absent | unclear |
| `external_evidence_limit_disclosed` | absent | covered-in-different-words |
| `known_context_not_reasked` | absent | unclear |
| `persistence_failure_checked` | absent | unclear |
| `limitations` | absent | covered-in-different-words |

LM Studio produced no usable structured proposal fields for the required checks.
Ollama surfaced several check labels and limitations-like material inside a
narrative payload, but left the contract fields `claimed_checks` and
`limitations` empty.

Dominant hypothesis to test next:

- B: context/contract legibility is the dominant hypothesis to test next.
- C: detection strictness may also be involved because some Ollama content was
  semantically adjacent but not placed in the expected fields.
- A: model weakness remains possible, especially for the empty LM Studio
  structured output.

Do not lower the validator bar based on these observations. Future work should
make the provider-facing contract more legible or diagnose detection behavior in
a separate, targeted change.

## Contract Legibility v0

The provider-facing context now includes an explicit contract and expected
structured output shape. This is a readability improvement only:

- validation logic is unchanged;
- status assignment is unchanged;
- `required_checks` logic is unchanged;
- provider claims are still untrusted;
- `claimed_checks` are not truth claims;
- DSM still validates form/honesty, not truth.

No expected business answer or coverage text is injected. Providers must write
their own substantive coverage. Offline tests prove the accept path remains
reachable with a conformant mock and that echoing check labels alone is not
accepted.

## Fenced Output Normalization v0

Observed with LM Studio `meta/llama-3.3-70b`: the model returned structured JSON
inside a markdown code fence. The gateway rejected safely because the fields were
not normalized into `structured_output`. This change adds structural
normalization only; validation criteria remain unchanged.

Normalization parses only. When `structured_output` is absent or has no
substantive contractual fields, the gateway extracts the first balanced JSON
object from `raw_output`, `narrative`, or `content` and hands it to the existing
validator. A real `structured_output` always wins and is never overwritten by
JSON found in narrative text. Parsed JSON does not imply `accepted_for_audit`:
the validator still decides, echo-only fenced JSON is still rejected, and a
provider self-status inside the JSON still cannot assign the DSM status.

## Observed Live Accepted Path — LM Studio / Llama 3.3 70B

After PR #43 (`provider-output-normalization-v0`), a manual live smoke was run
against LM Studio with `meta/llama-3.3-70b`. This is the first observed live
`accepted_for_audit` result.

Observed labels only:

- `validation_status`: `accepted_for_audit`
- warnings: none
- rejections: none
- audit produced: yes
- markdown produced: yes
- provider metadata: present
- input context hash: present
- raw output hash: present

This proves the live `accepted_for_audit` path is reachable with a sufficiently
capable local model and the fenced JSON normalization from PR #43. The earlier
`rejected_by_validator` result above remains the proven reject path; together they
show DSM discriminating on real live provider output.

Scope of the claim:

- This is proof of reachability from one live run.
- This does not prove repeatability or reliability.
- `accepted_for_audit` means the proposal was structured and honest enough to be
  audited by DSM.
- It does not mean factual truth.
- It does not mean a business decision was produced.
- It does not mean external verification or anchoring.

Manual substance review:

- The model claimed substantive coverage for:
  - `bug_before_feature`
  - `known_context_not_reasked`
  - `persistence_failure_checked`
- The model did not claim `external_evidence_limit_disclosed` as fully covered.
- It surfaced the missing or limited external evidence through coverage and
  limitations.
- `truth_claim` was false.
- No provider-supplied DSM status was accepted.
- No candidate rule was auto-promoted.

This is considered a merited `accepted_for_audit` because the provider covered
what it could and honestly surfaced what it could not cover.

No raw provider output, dogfood artifacts, or `.venv-live-smoke` data are
committed.

## Observed Cloud Provider Path — OpenAI / GPT-4o

A manual live smoke was run against OpenAI with `gpt-4o` through the existing
OpenAI-compatible provider path. This is the first observed cloud provider run
for Direction A (see `docs/design/daryl_for_chatgpt_v0.md`).

Observed labels only:

- `validation_status`: `accepted_for_audit`
- warnings: none
- rejections: none
- audit produced: yes
- markdown produced: yes
- provider metadata: present
- input context hash: present
- raw output hash: present

This observes the cloud provider path for Direction A: OpenAI as an untrusted
provider proposing into DSM through the existing Agent Proposal Gateway.

Scope of the claim:

- This proves the OpenAI provider path is reachable.
- This does not prove repeatability or reliability.
- `accepted_for_audit` does not mean factual truth, business decision approval,
  external verification, or external anchoring.
- DSM remains the authority over validation status.

Substance note:

The provider output was accepted for audit as structured and honest enough to
persist. It did not prove external evidence. The model included
`external_evidence_limit_disclosed` in `claimed_checks`, but its coverage text
stated that external evidence limits were not explicitly provided and recorded
this as a limitation. This is therefore an auditable/honest proposal form, not
proof that external evidence was actually supplied.

Security note:

No API key, API key fragment, raw provider output, full logs, dogfood artifacts,
or `.venv-live-smoke` data are committed.

## 5. Dogfood Artifacts

Use a separate dogfood data directory. The default is:

```text
.venv-live-smoke/agent-proposal
```

This path is covered by the repository `.venv*/` ignore rule. Do not point the
smoke at primary DSM memory.

To remove artifacts:

```bash
rm -rf .venv-live-smoke/agent-proposal
```

## 6. Why This Is Not in CI

CI must never contact a live model provider. The script refuses `--live` when
`CI=true`, and tests use the mock provider or mocked HTTP transport only.

The live smoke checks the provider trust boundary:

```text
live provider -> proposal -> DSM validation/status -> Agent Memory audit
```

It does not evaluate model quality and does not prove factual truth or
reasoning validity.
