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
