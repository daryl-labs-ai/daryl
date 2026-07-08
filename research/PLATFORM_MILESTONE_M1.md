# Platform Milestone M1 — Definition

**Status:** PENDING — awaiting Claude Desktop manual validation
**Date:** 2026-07-08
**Governs:** the first release that tells a complete story

---

## What M1 is

M1 is not a "version bump". It is the first release where the entire
architecture chain exists end-to-end:

```
Kernel (gelé) → DCP (gelé) → Conformance Suite → Providers → MCP → Hot Swap
```

Before M1, Daryl was a kernel with research. After M1, Daryl is a
protocol with providers and a demonstrated acceptance test.

---

## Release contents

| Component | Status | Evidence |
|-----------|--------|----------|
| Kernel DSM 1.0 | ✓ Frozen | 2026-03-14, intact, 1732 tests |
| ADR-0000 (Platform Doctrine) | ✓ Written | 7 invariants, 1 question |
| Continuity Doctrine | ✓ Frozen | 2026-07-08 |
| DCP v1.1 Specification | ✓ Frozen | 5 primitives, wire-compatible |
| DCP Compliance Suite (T1-T5) | ✓ Operational | Accepts compliant, rejects non-compliant |
| Goose MCP server + DCP primitives | ✓ Built | 16 tools (11 + 5 DCP), +198 lines |
| Zcode Continuity Provider | ✓ Certified | Hot Swap MVP, real SDK access |
| LM Studio Continuity Provider | ✓ Certified | Hot Swap MVP, real local LLM |
| Claude Continuity Provider | ✓ Built, ✓ Certified, **PENDING manual test** | Config written, T1-T5 pass, awaiting Claude Desktop restart |
| Hot Swap Demo v1 | **2/3 actors real** | Zcode + LM Studio completed loop; Claude awaits restart |

---

## The one remaining step

The gap between "READY_FOR_FIRST_REAL_DEMO" and "Real Demo Completed":

1. **Restart Claude Desktop**
2. **Prompt:** *"Call dsm_catch_up for project 'hotswap_v1_project'"*
3. Claude sees Zcode + LM Studio's 3 decisions
4. **Prompt:** *"Publish your decision with dsm_publish_receipt"*
5. **Verify:** `dsm_dcp_verify('hotswap_v1_project')` → OK
6. **Record the video**

If step 3 succeeds, M1 is complete. The full chain is demonstrated.

---

## The milestone-video convention

From M1 onward, every milestone is demonstrated by a video. The repo
shows the code; the release shows the proof.

| Milestone | Demo | Actors | Status |
|-----------|------|--------|--------|
| **M1** | Claude ↔ Zcode ↔ LM Studio | 3 real | PENDING Claude validation |
| **M2** | + ChatGPT | 4 real | NOT STARTED |
| **M3** | + Cursor | 5 real | NOT STARTED |
| **M4** | Multi-machine | cross-host | NOT STARTED |
| **M5** | Multi-developer | Alice → Bob → Agent | NOT STARTED |

Each milestone = one more real actor in the Hot Swap. The test never
changes. Only the number of real participants grows.

---

## What M1 proves (if Claude validation succeeds)

1. **A project survives agent replacement.** Claude → closed → Zcode →
   closed → LM Studio → closed → Claude returns and sees everything.
2. **The continuity protocol is real.** Three independent actors (cloud
   dev assistant, autonomous agent, local LLM) share memory via DCP.
3. **No copy/paste.** No manual context transfer. The project memory is
   the sole channel.
4. **Verifiable.** Every transition is receipt-backed. `verify_shard`
   confirms the chain.

---

## The observation that summarizes the journey

> *Il y a un an, Daryl était principalement un kernel. Aujourd'hui, si
> la dernière étape avec Claude Desktop se déroule comme prévu, Daryl
> devient un protocole démontré : le kernel reste le moteur, mais ce
> qui est visible pour un développeur est la capacité d'un projet à
> continuer entre plusieurs outils grâce à un contrat commun. C'est un
> changement de nature du projet, pas seulement une évolution de ses
> fonctionnalités.*

---

## M1 release checklist

- [x] Kernel frozen and intact
- [x] ADR-0000 written
- [x] Continuity Doctrine frozen
- [x] DCP v1.1 specification frozen
- [x] Compliance suite operational (T1-T5)
- [x] MCP server with DCP primitives (16 tools)
- [x] Zcode provider certified
- [x] LM Studio provider certified
- [x] Claude provider built + certified (T1-T5)
- [x] Claude Desktop MCP config written
- [x] Hot Swap v1 with Zcode + LM Studio (2/3 real)
- [ ] **Claude Desktop manual validation** ← THE remaining step
- [ ] Video recording
- [ ] M1 release on GitHub
