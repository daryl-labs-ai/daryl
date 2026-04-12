# Daryl — Demos

Two runnable demos that show what DSM actually does.

---

## 1. `demo_verify.py` — Tamper Detection

**What it proves:** DSM detects post-hoc modification of an agent's decision trail.

**Scenario:** A luxury AI advisor records a €120,000 watch recommendation.
Someone modifies the trail after the fact. DSM catches it.

```bash
python demo_verify.py
```

**What you'll see:**
- 7 entries recorded (start + 5 actions + end)
- Chain verified clean
- Trail modified: `price_eur 120000 → 45000`
- DSM detects the exact tampered entry
- Verdict: `TRAIL COMPROMISED`

---

## 2. `demo_end_to_end.py` — Multi-Agent Verifiable Causality

**What it proves:** DSM records and verifies decisions across multiple agents,
with cryptographic proof of causality and tamper detection per agent.

**Scenario:** Agent A (Luxury Advisor) delegates inventory analysis to Agent B
(Inventory Specialist). Both trails are recorded. Agent B's trail is tampered.
DSM pinpoints the compromised agent while Agent A remains intact.

```bash
python demo/demo_end_to_end.py
```

**What you'll see:**
- Agent A: 6 entries — intake, delegation, finalization
- Agent B: 5 entries — inventory analysis, recommendation, receipt
- Dispatch hash linking Agent A → Agent B: `VERIFIED`
- Trust receipt from Agent B: `INTACT`
- Agent B trail tampered: `price_eur 120000 → 45000`
- Agent A: still `OK`
- Agent B: `TAMPERED`
- Verdict: `AGENT B TRAIL COMPROMISED`

---

## What this demonstrates

| Capability | demo_verify | demo_end_to_end |
|---|:---:|:---:|
| Append-only recording | ✅ | ✅ |
| Hash chain integrity | ✅ | ✅ |
| Tamper detection | ✅ | ✅ |
| Multi-agent tracing | — | ✅ |
| Causal proof (dispatch) | — | ✅ |
| Cross-agent trust receipts | — | ✅ |
| Per-agent isolation | — | ✅ |

---

## Security insight

Receipts and `verify_shard` operate on two distinct layers:

- **Receipt** → proves an entry was published with a given hash at a given time
- **verify_shard** → recomputes hashes from raw content and detects any alteration

When content is modified without recomputing the stored hash:
the receipt confirms the entry was published,
`verify_shard` confirms the content was altered after publication.

> *Receipts prove publication. `verify_shard` proves integrity.
> Together, they make agent history admissible as evidence.*

---

## Output

`demo_end_to_end.py` also writes a structured decision report:

```
demo/outputs/decision_report.json
```

```json
{
  "client": "VIP_001",
  "decision": "recommendation",
  "item": "Patek Philippe 5711A",
  "price_eur": 120000,
  "agents": ["agent_a", "agent_b"],
  "causal_proof": "<dispatch_hash>",
  "receipt_status": "INTACT"
}
```
