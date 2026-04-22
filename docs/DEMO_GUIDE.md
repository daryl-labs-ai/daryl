# Demos

Four runnable demos that show what DSM does. Each creates its own temporary storage, runs to completion, and cleans up after itself. No configuration, no external dependencies, no network.

```bash
git clone https://github.com/daryl-labs-ai/daryl
cd daryl
pip install -e .
```

---

## 1. `demo_verify.py` — Tamper Detection

**What it demonstrates**: DSM detects post-hoc modification of an agent's decision trail.

**Why it matters**: If someone changes a recorded decision after the fact — adjusting a price, altering a rationale — the hash chain breaks. `verify_shard()` pinpoints the exact tampered entry.

**How to run**:

```bash
python demo/demo_verify.py
```

**What to look for**:

- 7 entries recorded (session start + 5 actions + session end)
- Chain verified clean: `status: OK`
- One entry modified: `price_eur 120000 -> 45000`
- Re-verification detects the tamper: `tampered: 1`, `chain_breaks` propagated
- Verdict: `TRAIL COMPROMISED`

The key insight: the hash was not recomputed after modification. This is what makes it detectable. Even if the attacker recomputes the modified entry's hash, the chain break propagates to every subsequent entry.

---

## 2. `demo/demo_end_to_end.py` — Multi-Agent Causality

**What it demonstrates**: Two agents collaborate. Agent A delegates to Agent B. DSM records both trails with cryptographic proof that B's work was in response to A's specific request.

**Why it matters**: In multi-agent systems, proving causality — not just correlation — between agent actions requires more than timestamps. The dispatch hash binds A's entry to B's task parameters. The trust receipt proves B completed the work.

**How to run**:

```bash
python demo/demo_end_to_end.py
```

**What to look for**:

- Agent A: 6 entries (intake, delegation, finalization)
- Agent B: 5 entries (analysis, recommendation, receipt)
- Dispatch hash verification: `VALID`
- Trust receipt verification: `INTACT`
- Agent B's trail tampered: `price_eur 120000 -> 45000`
- Agent A: still `OK` (isolated storage)
- Agent B: `TAMPERED`
- Receipt no longer reconciles with compromised storage

The key insight: each agent's trail is independently verifiable. Tampering one does not affect the other. But the receipt — issued before tampering — proves the original state.

---

## 3. `demo/demo_support_agent.py` — Real-World Policy Audit

**What it demonstrates**: A support agent handles a cancellation request, applies a 30% retention discount for a loyal customer. Someone removes the discount after the fact. DSM catches it.

**Why it matters**: This is the scenario regulators care about. Did the agent apply the correct policy? Can you prove it? The answer must come from the trail, not from someone's memory of what happened.

**How to run**:

```bash
python demo/demo_support_agent.py
```

**What to look for**:

- 6 entries recorded (start + classify_intent + check_subscription + apply_policy + confirm_response + end)
- Chain verified clean
- Policy entry modified: `discount_pct 30 -> 0`, rationale changed
- Re-verification detects the exact modified entry
- Verdict: `TRAIL COMPROMISED`

The key insight: the tamper changes a business decision (discount granted vs. denied). Without DSM, there would be no way to prove what the agent originally decided.

---

## 4. `demo_consumption_layer.py` — Full Consumption Layer

**What it demonstrates**: The complete DSM read path — recalling memory across sessions, packaging it under a token budget, and verifying its cryptographic origin.

**Why it matters**: Recording decisions is necessary but not sufficient. An agent must also be able to recall relevant past decisions, receive them in a format that fits its context window, and trust that the recalled information has not been altered. This demo shows all three.

**How to run**:

```bash
python demo/demo_consumption_layer.py
```

**What to look for**:

**ACT 1 — Setup**: Three sessions written across 45 days. Session 1 decides "use REST." Session 2 supersedes with "use gRPC." Session 3 is the current session.

**ACT 2 — Recall** (`search_memory`):
- Matches found across past sessions, ranked by relevance
- Newer gRPC decision scores higher than older REST decision
- REST decision marked `superseded` (a newer entry covers the same query tokens)
- Older entries marked `outdated` (>30 days)
- Verified claims extracted from `action_result` entries

**ACT 3 — Context** (`build_context`):
- Memory packaged into a `ContextPack` with sections: system_facts, past_session_recall, verified_claims
- Token estimate reported
- `build_prompt_context()` renders the pack as a string ready for LLM injection

**ACT 4 — Provenance** (`build_provenance`):
- Full chain verification: `integrity=OK`, `trust_level=verified`
- `broken_chains=0`
- Source shards and entry hashes traced

**ACT 5 — Summary**: All three phases reported cleanly.

The key insight: the older REST decision is not deleted or hidden. It is still present in the trail and still verifiable. But the temporal analysis correctly identifies it as superseded, and the context pack ranks the newer gRPC decision higher. History is preserved; relevance is computed.

---

## Comparison

| Capability | demo_verify | demo_end_to_end | demo_support_agent | demo_consumption_layer |
|---|:---:|:---:|:---:|:---:|
| Append-only recording | x | x | x | x |
| Hash chain integrity | x | x | x | x |
| Tamper detection | x | x | x | - |
| Business scenario | - | - | x | x |
| Multi-agent tracing | - | x | - | - |
| Causal proof (dispatch) | - | x | - | - |
| Cross-session recall | - | - | - | x |
| Temporal superseded detection | - | - | - | x |
| Token-budgeted context | - | - | - | x |
| Provenance verification | - | - | - | x |
