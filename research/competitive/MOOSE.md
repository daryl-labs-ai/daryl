# MOOSEnger / AutoMOOSE — Competitive Product Memo

**Program:** 2026-CompetitiveProductResearch
**Product:** MOOSEnger (arXiv:2603.04756) and AutoMOOSE (arXiv:2603.20986)
**Tested:** NOT TESTED — these are research prototypes, not installable
products.
**Classification discipline:** every claim is tagged OBSERVED / NOT TESTED.

---

## 1. Executive Summary

MOOSEnger and AutoMOOSE are **academic research prototypes** for the MOOSE
(Multiphysics Object-Oriented Simulation Environment) ecosystem. They are
not installable products, not on PyPI under those names, and not relevant
as competitors to Daryl. This memo documents the failure to test them
honestly rather than inventing observations.

---

## 2. What these tools actually are (OBSERVED via web search)

- **MOOSEnger** (arXiv:2603.04756): a tool-enabled AI agent that translates
  natural language into runnable MOOSE simulation configurations using RAG.
  It is a research paper describing a prototype, not a product.
- **AutoMOOSE** (arXiv:2603.20986): an agentic framework that automates
  the full lifecycle of MOOSE phase-field simulation from a natural-language
  prompt. Also a research paper.
- The `moose` package on PyPI (v0.9.8) is **unrelated** — it is an
  abandoned package that fails to build (`Failed to build 'moose'`).

**Category:** domain-specific research prototypes for computational
multiphysics simulation. Not agent frameworks, not memory systems, not
products.

---

## 3. Why they could not be tested (NOT TESTED)

1. Neither MOOSEnger nor AutoMOOSE is published as an installable package.
2. They are arXiv papers describing prototypes built on the MOOSE framework
   (a C++ simulation environment for nuclear engineering / multiphysics).
3. The MOOSE framework itself requires a full C++ build toolchain and is
   unrelated to Python agent/memory infrastructure.
4. The PyPI `moose` package is unrelated and broken.

**Decision:** documenting the failure honestly rather than simulating a
test of a research paper.

---

## 4. Relevance to Daryl (INFERRED)

Even if these tools were installable, they are **not in Daryl's category**.
They are domain-specific agents for simulation configuration, not memory or
coordination layers. The question *"where is the verifiable proof of each
decision"* is relevant in principle (an agent configuring physics
simulations should prove its configuration choices), but:

- The tools are not available to test.
- Their domain (multiphysics simulation) is orthogonal to Daryl's
  (operational memory for AI agents).

**No competitive signal. No complementary signal. Not a relevant
candidate.**

---

## 5. Conclusion

MOOSEnger and AutoMOOSE are academic prototypes in a different domain. They
do not belong in a competitive analysis of agent memory systems. This memo
exists only to document that the investigation was attempted and the
candidate was excluded for documented reasons, not skipped.

**Classification: NOT RELEVANT. Not tested.**
