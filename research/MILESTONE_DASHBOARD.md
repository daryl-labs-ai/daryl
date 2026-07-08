# Daryl Platform — Milestone Dashboard

**Governance:** a milestone is Released only when all four columns are green.
No column is skipped. No column is backfilled.

---

## Dashboard

| Milestone | Code | Conformance | Demo (video) | External user | Status |
|-----------|:----:|:-----------:|:------------:|:-------------:|:------:|
| **M1** — Claude ↔ Zcode ↔ LM Studio | ✅ | ✅ T1-T5 | ✅ passed | ⏳ pending | **RC** |
| **M2** — + ChatGPT | ⏳ | ⏳ | ⏳ | ⏳ | Planned |
| **M3** — + Cursor | ⏳ | ⏳ | ⏳ | ⏳ | Planned |
| **M4** — Multi-machine | ⏳ | ⏳ | ⏳ | ⏳ | Planned |
| **M5** — Multi-developer | ⏳ | ⏳ | ⏳ | ⏳ | Planned |

---

## Column definitions

### Code
The implementation exists in the repository, tests pass, kernel is intact.

### Conformance
The DCP Compliance Suite (T1-T5) passes for every provider in the milestone.

### Demo
A video exists showing the Hot Swap running end-to-end with all milestone
actors as **real** (zero simulation). The video is < 2 minutes and requires
no architecture explanation to understand.

### External user
At least one developer **outside the core team** has followed the Quick
Start guide, reproduced the Hot Swap, and confirmed it works. This is the
proof that the experience is real, not just internally validated.

---

## M1 remaining steps

For M1 to move from **RC** to **Released**:

- [x] **Demo**: Claude Desktop → `dsm_catch_up` → sees Zcode + LM Studio → `dsm_publish_receipt` → `dsm_dcp_verify` → VerifyStatus.OK — **PASSED 2026-07-08**
- [ ] **External user**: Share the Quick Start guide with one developer outside the team → they reproduce the Hot Swap → they confirm

When the external user confirms, M1 = Released.

---

## The rule

> A milestone is not Released until someone who did not build it can reproduce it.

This is the shift from technical pilotage to proof-based pilotage. The
question is no longer *"does it work?"* (answered by code + conformance).
The question is *"can someone else make it work?"* (answered by demo +
external user).
