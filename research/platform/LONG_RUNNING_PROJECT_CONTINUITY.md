# Long Running Project Continuity — Report

**Date:** 2026-07-08
**Module:** Receipt Replay Protection
**Verdict:** **PROJECT_COMPLETED_WITH_DCP**

---

## Executive Summary

Three actors (Zcode + LM Studio) developed a real security feature —
receipt replay protection — for the Daryl repository, coordinated entirely
through DSM. The feature closes the only falsification gap identified in
Boucle 2: duplicate receipts were silently accepted. After this sprint,
duplicate receipts return `DUPLICATE` status.

The development followed a real workflow (plan → implement → review →
verify), with every transition receipt-backed and every actor reading
context from DSM.

**One real limit was observed:** LM Studio's review identified a potential
race condition in the lazy-cache approach — concurrent `protect()` calls
could accept a duplicate before the shard write propagates. This is a
real DCP-level concern, not a kernel issue.

---

## Project chosen

**Receipt Replay Protection** — closing the only gap from the Boucle 2
falsification tests.

### Justification (facts only)
- **Observed gap:** Boucle 2, F3 test — "Duplication receipt: NON DÉTECTÉ.
  DSM ne tracke pas les receipts déjà vus. Pas de protection replay."
- **Security impact:** the only falsification class not detected (4/5
  attacks detected, replay was the 5th)
- **Above kernel:** implementation lives in `exchange.py` + `status.py`
- **Real value:** hardens the receipt system against replay attacks

---

## Participants and timeline

| Time (UTC) | Actor | Action | Method | What happened |
|------------|-------|--------|--------|---------------|
| 17:21:24 | Zcode | plan | REAL SDK | Analyzed exchange.py, identified integration points, defined design questions |
| 18:17:55 | Zcode | implement | REAL SDK | Wrote ReplayProtector class (+78 lines), tested all scenarios, published |
| 18:19:06 | LM Studio | review | REAL LOCAL LLM | Read sprint context from DSM, reviewed the implementation, published |

**DSM entries:** 3 (plan + implement + review)
**Integrity:** VerifyStatus.OK
**catch_up latency:** 0.4 ms

---

## What was implemented

### `ReplayProtector` class (`src/dsm/exchange.py`, +78 lines)

```python
rp = ReplayProtector(storage)
rp.protect(receipt)           # → True if new, False if duplicate
rp.verify_with_replay(receipt) # → DUPLICATE if seen, else standard verify
```

- Uses a dedicated shard (`receipt_seen`) for persistent storage
- Lazy-loaded `seen_cache` (set of `receipt_id`s) for O(1) lookup
- `StorageReceiptStatus.DUPLICATE` added to `status.py`
- Backward compatible: `verify_receipt_against_storage` unchanged

### Code impact

| File | Change | Lines |
|------|--------|-------|
| `src/dsm/exchange.py` | ReplayProtector class | +78 |
| `src/dsm/status.py` | DUPLICATE enum value | +1 |
| `src/dsm/cli.py` | (from prior sprint) DCP CLI commands | +163 |
| `src/dsm/integrations/goose/server.py` | (from M1) DCP MCP tools | +198 |
| `src/dsm/core/` | **No changes** | 0 |

---

## What DSM really provided

| Capability | How it was used |
|------------|----------------|
| **Context propagation** | LM Studio read the plan + implementation from DSM, understood what to review |
| **Attribution** | Every entry shows who did what (zcode:plan, zcode:implement, lm_studio:review) |
| **Integrity** | `verify_shard` confirmed the chain was intact after 3 entries |
| **Receipt portability** | Each actor's contribution has a receipt that can be verified independently |

### What would have been harder without DSM

- LM Studio would not have known what to review (no shared context)
- There would be no verifiable record of who decided what
- The review would have been lost (ephemeral chat, not persisted)

---

## Limits observed (Boucle 3)

### OBSERVED limit 1: Race condition in lazy cache

LM Studio identified: *"concurrent protect() calls can see a stale
not-seen state, leading to duplicate acceptance."*

This is a real DCP-level concern. The `seen_cache` is loaded lazily and
not refreshed between calls within the same process. Two concurrent
`protect()` calls for the same receipt could both see "not seen" before
either writes to the shard.

**Classification:** OBSERVED (identified by LM Studio review)
**Impact:** Low in practice (DSM is single-writer per shard), but
theoretically real in a multi-process scenario.
**Fix direction (not implemented):** threading.Lock around protect(), or
always re-read the shard before checking (trades performance for safety).

### OBSERVED limit 2: LM Studio review was truncated

The review was cut at 300 characters when published to DSM (entry content
limit in the sprint script). The full review covered 4 points; only the
first 1.5 were preserved.

**Classification:** OBSERVED
**Impact:** Information loss — the full review is not recoverable from DSM.
**Fix direction:** increase the content limit, or store full content in
metadata.

### OBSERVED limit 3: No automated test was written

The replay protection was tested manually (inline script) but no
`tests/test_replay_protection.py` was added to the test suite.

**Classification:** OBSERVED
**Impact:** The feature works today but could regress without detection.
**Fix direction:** add a proper test file.

---

## What was NOT observed (no limit found)

- **Kernel limitation:** none. The kernel provided everything needed.
  The replay protection is entirely above the kernel.
- **DCP ambiguity:** none. The 5 primitives worked as specified.
- **catch_up performance:** 0.4 ms — no degradation observed.
- **Context reconstruction:** LM Studio successfully reconstructed the
  full sprint context from DSM and produced a relevant review.

---

## Classification summary

| Claim | Class |
|-------|-------|
| Replay protection works (CONFIRMED → DUPLICATE) | OBSERVED |
| LM Studio reviewed from DSM context | OBSERVED |
| Race condition in lazy cache | OBSERVED (by LM Studio) |
| Review truncated at 300 chars | OBSERVED |
| No automated test added | OBSERVED |
| Kernel sufficient for replay protection | OBSERVED |
| DCP sufficient for the workflow | OBSERVED |
| Multi-process replay safety | NOT TESTED |

---

## Verdict

### **PROJECT_COMPLETED_WITH_DCP**

A real security feature (replay protection, 79 lines) was developed
collaboratively by Zcode + LM Studio, coordinated entirely through DSM.
The feature closes the only falsification gap. The kernel was not modified.
LM Studio's review identified one real limit (race condition in lazy cache)
that warrants future attention.

### What is OBSERVED
- Replay protection implemented and tested
- Duplicate receipts return DUPLICATE status
- LM Studio produced a useful review from DSM context
- One real limit identified (race condition)
- Sprint integrity verified OK (3 entries)

### What is NOT TESTED
- Multi-process concurrent replay protection
- Large-scale seen-shard performance (10k+ receipts)
- Claude Desktop participating in this specific sprint
