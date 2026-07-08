# Daryl Platform — Proof Portfolio

**Status:** Living document. Each proof answers a different question.
A proof is only valid when someone who didn't build it can reproduce it.

---

## The portfolio

| # | Proof | Question answered | Status |
|---|-------|-------------------|--------|
| 1 | **Hot Swap M1** | Le projet survit-il au changement d'outil ? | ✅ PASSED |
| 2 | **Project Continuity Sprint** | Peut-on développer un vrai module avec DCP ? | ✅ PASSED |
| 3 | **External Reproduction** | Un tiers peut-il reproduire ces résultats ? | ⏳ pending |
| 4 | **Multi-machine** | La continuité fonctionne-t-elle entre plusieurs postes ? | ⏳ pending |
| 5 | **Multi-developer** | Deux personnes peuvent-elles collaborer via DCP ? | ⏳ pending |

---

## Proof 1 — Hot Swap M1

**Question:** *Le projet survit-il au changement d'outil ?*

**What was proven:**
- 3 real actors (Zcode + LM Studio + Claude Desktop) shared project memory
- Claude read what Zcode + LM Studio wrote, without copy/paste
- All receipts verified, integrity maintained
- The project continued across cloud assistant → local LLM → cloud assistant

**Evidence:** Hot Swap v1 report (`research/platform/HOT_SWAP_V1_CLAUDE_ZCODE_LMSTUDIO.md`)

**Classification:** OBSERVED

---

## Proof 2 — Project Continuity Sprint

**Question:** *Peut-on développer un vrai module avec DCP ?*

**What was proven:**
- A real module (5 CLI commands, 163 lines) was developed collaboratively
- Workflow: plan → implement → review → verify — not just agent handoff,
  but a **development workflow**
- LM Studio produced a genuine technical review from DSM context
- Every transition was receipt-backed
- Kernel intact, 1731 tests pass

**Evidence:** Sprint report (`research/platform/COLLABORATIVE_MODULE_SPRINT.md`)

**Classification:** OBSERVED

---

## The shift this portfolio represents

Proof 1 demonstrated **agent succession**:

```
Agent A → Agent B → Agent C
```

Proof 2 demonstrated **development workflow continuity**:

```
Plan → Implementation → Review → Tests → Deliverable
```

These are different validations. The first proves the substrate. The second
proves the substrate supports real work.

---

## Next priority

No new features. No new providers. No new protocol.

1. Publish M1 RC (with video)
2. Publish Project Continuity Sprint (as second proof)
3. Find one external developer to reproduce both
4. Collect feedback

External reproduction is the proof that converts "it works for us" into
"it works." For infrastructure, that conversion is worth more than any
new primitive.
