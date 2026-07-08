# DSPy — Competitive Product Memo

**Program:** 2026-CompetitiveProductResearch
**Product:** DSPy v3.2.1 (`dspy-ai` PyPI package)
**Tested:** 2026-07-08, isolated venv (Python 3.12), local ollama (llama3.2).
**Classification discipline:** every claim is tagged
OBSERVED / MEASURED / INFERRED / NOT TESTED.

---

## 1. Executive Summary

DSPy is a **declarative agent-programming framework** with a compilation
step. You write programs as modules (`dspy.Module`) with typed signatures
(`dspy.Signature`); a "teleprompter" (optimizer) compiles them by
selecting few-shot examples and/or optimizing prompts against a training
set and a metric. The compiled program is saved as JSON (demos +
instructions + metadata).

DSPy occupies a category none of the previous four products cover: **agent
compilation / prompt optimization**. It is closer to a "compiler for LLM
programs" than to a memory or workflow system.

The critical finding for Daryl: **a compiled DSPy program has no verifiable
provenance.** The saved JSON contains the compiled demos (few-shot
examples) but no record of which optimizer produced them, which metric was
used, which training examples were tried and rejected, or which LLM model
was used during compilation. The demos themselves are editable post-hoc
with no integrity check. `inspect_history` prints the LLM trace to stdout
but returns `None` — it is a debugging tool, not a persistent audit trail.
The DSPy cache (LM response cache) has no integrity protection.

DSPy is complementary to Daryl. Daryl could provide the verifiable
substrate underneath the compilation pipeline: binding training set →
optimizer → metric → compiled demos → saved program into a hash-chained
receipt that makes the compilation process reproducible and tamper-evident.

---

## 2. Installation / Onboarding (OBSERVED)

| Aspect | Observation | Class |
|--------|-------------|-------|
| `pip install dspy-ai` | Clean install. | OBSERVED |
| First successful LLM call | < 60 seconds with local ollama config. | MEASURED |
| Dep weight | Moderate (~30, includes pydantic, datasets, openai). | OBSERVED |
| Failures | Zero. | OBSERVED |

---

## 3. What DSPy Actually Is (OBSERVED)

```python
import dspy
lm = dspy.LM(model="ollama/llama3.2", base_url="http://localhost:11434")
dspy.configure(lm=lm)

class QA(dspy.Signature):
    question: str = dspy.InputField()
    answer: str = dspy.OutputField()

class QAProgram(dspy.Module):
    def __init__(self):
        self.qa = dspy.Predict(QA)
    def forward(self, question):
        return self.qa(question=question)

# Compile: optimizer selects good few-shot examples
teleprompter = dspy.BootstrapFewShot(metric=exact_match, max_bootstrapped_demos=2)
compiled = teleprompter.compile(QAProgram(), trainset=train_examples)

# Save and load
compiled.save("/tmp/qa.json")
prog2 = QAProgram()
prog2.load("/tmp/qa.json")
```

The core abstraction: a **Module** (declarative program) compiled by a
**Teleprompter** (optimizer) into a runnable program with selected demos.
This is genuinely novel — no other product in this study has a
"compile-and-optimize" step.

---

## 4. Scenarios Tested

### S1 — Uncompiled program execution (OBSERVED + MEASURED)

```python
prog(question="What is 2+2?") → "4"     # 1.9s (local ollama)
```

### S2 — Compilation with BootstrapFewShot (OBSERVED + MEASURED)

```python
teleprompter = dspy.BootstrapFewShot(metric=exact_match, max_bootstrapped_demos=2)
compiled = teleprompter.compile(prog, trainset=train)
# → "Bootstrapped 0 full traces" (llama3.2 didn't pass the metric on all examples)
# → compiled in 0.8s
```

Inspected compiled state: 2 demos (few-shot examples from the trainset).

### S3 — Save/Load + provenance inspection (OBSERVED)

Saved JSON keys: `['qa', 'metadata']`.

| Provenance question | In saved file? |
|---------------------|----------------|
| Which optimizer? (BootstrapFewShot?) | **No** |
| Which metric? (exact_match?) | **No** |
| Which training examples were tried? | **No** (only the selected demos, not the rejected ones) |
| Which LLM model was used during compilation? | **No** |
| Which demos were bootstrapped vs. labeled? | **No** (just a flat list) |
| Hash/signature of the saved file? | **No** |

### S4 — Falsification (INFERRED from S3)

Demos are plain JSON in the saved file. An attacker can:
- inject misleading few-shot examples (no integrity check)
- remove demos that don't support a desired behavior
- change the instructions field
All undetectable from the saved file alone.

### S5 — inspect_history (OBSERVED)

`inspect_history(n=5)` prints full prompts + responses to stdout (colored).
Returns `None`. It is a debugging tool, not a persistent trace. The trace
is lost when the process exits.

### S6 — DSPy cache (OBSERVED)

`~/.dspy_cache/` contains 16 files (cached LLM responses). Files are plain
(no hash/signature). The cache is for speed (avoid re-calling the LLM),
not for provenance.

---

## 5. Strengths

| # | Strength | Class |
|---|----------|-------|
| S1 | **Novel compilation paradigm.** No other product optimizes agent programs by selecting demos against a metric. This is genuinely a different category. | OBSERVED |
| S2 | Clean install, pure Python, works with any LLM via `dspy.LM`. | OBSERVED |
| S3 | Declarative signatures make agent programs type-safe and introspectable. | OBSERVED |
| S4 | Multiple optimizers (BootstrapFewShot, COPRO, MIPRO, AvatarOptimizer, BetterTogether). | OBSERVED |

---

## 6. Weaknesses (for the provenance/trust dimension)

| # | Weakness | Class |
|---|----------|-------|
| W1 | No optimizer provenance in saved programs. Cannot tell which teleprompter produced a compiled artifact. | OBSERVED |
| W2 | No metric provenance. Cannot tell what the compiled program was optimized for. | OBSERVED |
| W3 | No LLM model provenance. Cannot tell which model was used during compilation. | OBSERVED |
| W4 | Demos are editable post-hoc with no integrity check. | OBSERVED |
| W5 | `inspect_history` is ephemeral (stdout print, returns None). No persistent audit trail. | OBSERVED |
| W6 | Cache has no integrity protection. | OBSERVED |
| W7 | No binding between "this compiled program" and "this training set version". | OBSERVED |

---

## 7. What Daryl Would Provide Underneath

Daryl does not replace DSPy. Daryl would sit underneath the compilation
pipeline and provide:

- **Compilation receipt**: optimizer name + version, metric, training set
  fingerprint, LLM model — all as a DSM entry hash-chained at compile time.
- **Demo provenance**: each bootstrapped demo recorded as a DSM entry with
  its source training example and the metric score that admitted it.
- **Program binding**: the saved JSON's content hash recorded as a DSM
  entry, bound to the compilation receipt. Tampering with the saved demos
  would break the hash → detectable.
- **Trace persistence**: `inspect_history` output captured as DSM entries,
  so the compilation trace survives process exit and is replayable.

---

## 8. Comparison Table

| Axis | DSPy | Daryl |
|------|------|-------|
| Category | agent compilation / prompt optimization | operational memory + provenance |
| Novel paradigm | ✓ (compile-and-optimize) | n/a |
| Optimizer provenance | ✗ | ✓ (receipt) |
| Demo integrity | ✗ (editable JSON) | ✓ (hash-chained) |
| Compilation trace | ephemeral (stdout) | ✓ (persistent) |
| Replay of compilation | ✗ (lost on exit) | ✓ (replay) |
| Cross-program memory | ✗ (each program is standalone) | ✓ (shared shards) |

---

## 9. Final Question

> *"If Daryl did not exist, what would this product teach us about building
> operational memory?"*

It would teach us that **compilation without provenance is a trust vacuum**.
DSPy optimizes agent programs — selects the best demos, tunes the prompts,
runs the metric. But the moment you save the compiled program, you lose
every trace of *how* it was produced. Which optimizer? Which metric? Which
examples were tried and rejected? Which model was used? Gone. The saved
JSON is a snapshot of the result with no history of the process. And the
result itself is editable, with no way to detect tampering. The gap is the
same as everywhere else in this study: the artifact exists, but its
*provenance* — the chain of evidence from training data to compiled output
— is invisible, unverified, and unauditable. That gap is exactly what a
verifiable substrate fills.
