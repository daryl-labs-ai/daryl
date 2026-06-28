# Daryl — Evidence Book

**Status:** Evidence · **Date:** 2026-06-27 · **Regime:** `declared` · **Expected to date — that is its job.**

The third of three documents, kept apart on purpose:

- **Manifesto** (`VISION_KNOWLEDGE_FABRIC.md`) — near-timeless. *Why* the product exists.
- **ADRs** (`ADR-PRL-000x`) — the binding law. *What* the rules are.
- **Evidence Book** (this file) — the dated proofs that the constitution is *operational today*.

The manifesto must not carry commit hashes, benchmark numbers, or "as of" claims — they would date a
text meant to last years. Those live here, and they are *supposed* to age. When someone asks "does
this actually work?", this is the file that answers, with specifics.

## Proof #1 — Retrieval v2: a buried decision recalled (2026-06-27)

The first living proof that the Fabric's recall layer is operational on the real corpus.

- **The case.** The decision *`Storage.append` vs `execute_action`* (gold `fe732b68`, a 384-message
  thread with a misleading title) — the kind of buried decision a conversation-centric tool loses.
- **The arc, measured.** Experiments A→F on a 15-question human-ratified benchmark eliminated each
  wrong design in turn (not the binder, not ranking, not the 200-char preview, not chunking, not RRF,
  not symmetric fusion) and converged on the ratified policy `chunk_primary` (gate 10, k 10,
  chunk 500). Full record: `PRL_RETRIEVAL_V2_FINDINGS.md`.
- **The real run, through production code.** On the raw export: ingestion fixed (F1), full-text format
  aligned to the eval (F2), recall depth decoupled from output (F3) → `fe732b68` went rank 32 → 6 →
  **#1 at `-k 5 --candidate-k 50`**, cache-loaded (~9.6 s, zero re-embedding). Eval↔prod parity
  confirmed (Top-3/Top-5 exact). Closure: `RETRIEVAL_V2_CLOSURE.md`.
- **State.** Delivered + frozen on `main` (R1–R3 + F1–F3, PRs #65–#70; through-prod validated), six
  strictly-additive PRs, kernel untouched.

> Manifesto claim it backs: *"Retrieval — the first living proof that the constitution is operational:
> a buried decision is recalled, not the thread."*

## How to add to this book

Each future proof (a benchmark, a demo, a customer case study) gets its own dated entry here, with the
specifics, and a one-line pointer to the manifesto claim it supports. Keep the specifics out of the
manifesto; keep the meaning out of this book.

## Source records (the detailed evidence)

- `PRL_RETRIEVAL_V2_FINDINGS.md` — the full A→F experiment arc + eval↔prod skew + resolution.
- `RETRIEVAL_V2_CLOSURE.md` — delivery, the truth-test table, the canonical command, the freeze.
- `eval/` (local, git-excluded) — the harness, ratified questions, and reports (privacy: metadata only).
