# DCP Specification Sufficiency — Test Report

**Date:** 2026-07-08
**Question answered:** *La spécification DCP est-elle suffisante pour être
implémentée indépendamment, sans le SDK de référence ?*
**Answer:** **YES — and the two implementations are wire-compatible.**

---

## What was built

### ToyDCPProvider (`research/providers/toy_provider/provider.py`)

A complete DCP v1.1 provider implemented **from the specification only**.

- **339 lines** of pure Python
- **Zero imports** from `dsm`, `dsm_primitives`, or any Daryl package
- Only dependencies: `json`, `hashlib`, `os`, `datetime`, `pathlib`
- Implements all 5 DCP v1.1 primitives: `join_project`, `catch_up`,
  `publish_receipt`, `verify`, `project_context`
- Computes the DSM v1 canonical hash from the ADR-0002 formula, not from
  an imported function

### DCP Conformance Suite (`test_dcp_conformance.py`)

5 tests (T1-T5) that validate any DCP provider against the specification.

---

## Results

### Conformance suite (T1-T5)

```
T1_join_project           ✓ PASS
T2_publish_receipt        ✓ PASS
T3_catch_up               ✓ PASS
T4_verify                 ✓ PASS
T5_hot_swap               ✓ PASS

DCP 1.1 Core Certified
```

### Cross-implementation wire compatibility

The decisive test: can the toy provider (spec-only) and the real DSM
kernel (reference implementation) share the same storage?

| Step | Who writes | Who reads | Result |
|------|-----------|-----------|--------|
| 1 | DSM kernel | Toy provider | **YES** — toy reads kernel entry |
| 2 | DSM kernel | Toy provider verify | **YES** — toy verifies kernel's hash chain |
| 3 | Toy provider | DSM kernel | **YES** — kernel reads toy's entry |
| 4 | Toy provider | DSM kernel verify | **YES** — kernel verifies toy's hash as OK |

**Verdict: WIRE-COMPATIBLE.** Two independent implementations — one built
from the SDK, one built from the spec alone — share the same storage,
read each other's entries, and verify each other's hash chains.

---

## What this proves

1. **The DCP specification is sufficient.** A developer with no access
   to the Daryl SDK, reading only `DCM_CONTINUITY_PROTOCOL_v1.md` and
   `DCP_v1.1_AMENDMENT.md`, can build a working provider.

2. **The canonical hash formula is reproducible.** The toy provider
   computes `v1:sha256(canonical_json(entry))` independently and produces
   hashes the kernel verifies as valid. The ADR-0002 spec is precise
   enough for independent reimplementation.

3. **The storage format is a stable wire protocol.** JSONL + segment
   naming + integrity pin format are interoperable across implementations.
   This means a third-party provider can read/write the same data directory
   as the kernel.

4. **DCP is not theoretical.** It has two independent implementations
   that are mutually compatible. This is the minimum requirement for a
   protocol to be called real.

---

## Classification

| Claim | Class |
|-------|-------|
| Toy provider passes T1-T5 | **OBSERVED** (test output) |
| Toy provider reads kernel data | **OBSERVED** (cross-test step 1) |
| Toy provider verifies kernel hash chain | **OBSERVED** (cross-test step 2) |
| Kernel reads toy provider data | **OBSERVED** (cross-test step 3) |
| Kernel verifies toy provider hash | **OBSERVED** (cross-test step 4) |
| DCP spec is sufficient for independent implementation | **OBSERVED** (the toy provider IS that implementation) |
| Third-party teams will adopt DCP | **HYPOTHESIS** (depends on factors outside this repo) |

---

## What this means for DCP maturity

```
Level 1: Internal protocol    ← WAS HERE (Zcode + LM Studio via SDK)
Level 2: Open protocol        ← HERE NOW (spec + conformance suite + independent impl)
Level 3: Ecosystem standard   ← NOT YET (requires third-party adoption)
```

DCP just moved from Level 1 to Level 2. The specification has a conformance
suite and a proof-of-concept independent implementation. Any team can now
read the spec, run the suite, and certify their provider.

---

## The sentence that changed

For a year: *"Que doit contenir DSM ?"*
Today: *"Que doit implémenter un acteur pour participer à la continuité
d'un projet ?"*

The toy provider answers the second question: **read the spec, implement
5 primitives, pass 5 tests.** That is all it takes to participate in
project continuity.

---

## Artifacts

```
research/providers/
├── toy_provider/
│   ├── provider.py                  ← spec-only implementation (339 lines)
│   └── test_dcp_conformance.py      ← T1-T5 conformance suite
└── DCP_SPEC_SUFFICIENCY_REPORT.md   ← this report
```

The kernel is intact. The specification is proven sufficient. DCP is
wire-compatible across independent implementations.
