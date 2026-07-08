# Hot Swap — Adapter-First Roadmap

**Status:** The protocol is proven. The path is now incremental adapter
validation, not new tests.

---

## The discovery restated precisely

It is not merely "DSM is model-agnostic." It is:

> **The continuity protocol is independent of the inference engine.**

```
GPT-5   Claude   Nemotron   Qwen   DeepSeek   Llama
  │        │        │         │        │        │
  └────────┴────────┴─────────┴────────┴────────┘
                    │
          DSM Continuity Protocol
          (catch_up + publish_receipt + verify)
```

The protocol matters more than any individual model. This is what happens
when a technology moves from feature to infrastructure.

---

## The roadmap update

The Hot Swap is no longer a one-time demo to build towards. It is the
**permanent acceptance test** for every new adapter.

```
BEFORE:                              NOW:
Hot Swap → SDK → Adapters → Demo     Claude Adapter → Hot Swap v1
                                     ChatGPT Adapter → Hot Swap v2
                                     Cursor Adapter → Hot Swap v3
```

Each adapter is immediately validated by the same scenario. No new tests
need to be invented. The Hot Swap is the standing benchmark.

---

## Version targets

### Version 1 — Three Real Actors (next milestone)

```
Claude Desktop (real, via MCP adapter)
       ↓
   Zcode (real, via SDK)
       ↓
   LM Studio (real, via local API)
       ↓
Claude Desktop (returns)
```

**Threshold:** 3/3 actors real. No simulation.

**What it proves:** The continuity protocol works across cloud dev
assistant + autonomous agent + local LLM, with zero copy/paste and zero
manual context transfer.

**What it needs:**
- DSM MCP server: add `dsm_catch_up` + `dsm_publish_receipt` tools (~1 day)
- Claude Desktop: configure to use the DSM MCP server (~hours)
- Zcode + LM Studio: already real

### Version 2 — Add ChatGPT Desktop

**Threshold:** 4/4 actors real.

**What it needs:** A ChatGPT bridge (clipboard, OpenAI API, or browser
automation). ChatGPT Desktop has no automation API, so this requires
design work.

### Version 3 — Add Cursor

**Threshold:** 5/5 actors real.

**What it needs:** A Cursor adapter (rules/plugin system or MCP if Cursor
supports it).

---

## The public demo format

Not a benchmark. Not an article. A **video**.

```
LEFT:        Claude Desktop
CENTER:      DSM (visible: catch_up output, receipts)
RIGHT:       LM Studio

Claude works → Claude closes
LM Studio opens → "Continue project X" → continues automatically
LM Studio closes
Claude reopens → "Continue project X" → continues automatically
```

No copy/paste. No summary. No manual history. Just: *"Continue project X."*

If a viewer sees this and understands the value in 60 seconds without
explanation, the demo passes.

---

## The standing benchmark

From now on, every adapter, every SDK change, every platform evolution is
measured against the same test:

> **Does the Hot Swap still pass? How many actors are real?**

| Version | Real actors | Simulated | Status |
|---------|-------------|-----------|--------|
| MVP (today) | 2 (Zcode, LM Studio) | 3 | OBSERVED |
| v1 (next) | 3 (Claude, Zcode, LM Studio) | 0 | NOT TESTED |
| v2 | 4 (+ChatGPT) | 0 | NOT TESTED |
| v3 | 5 (+Cursor) | 0 | NOT TESTED |

Each version is a milestone. Each milestone is a Hot Swap with more real
actors. The test never changes — only the number of real participants
grows.
