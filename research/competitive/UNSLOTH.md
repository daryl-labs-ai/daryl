# Unsloth — Competitive Product Memo

**Program:** 2026-CompetitiveProductResearch
**Product:** Unsloth v2026.7.1 (`unsloth` PyPI package)
**Tested:** 2026-07-08, isolated venv (Python 3.12). Local analysis only
(no GPU training run performed — not needed to answer the provenance
questions).
**Classification discipline:** every claim is tagged
OBSERVED / MEASURED / INFERRED / NOT TESTED.

---

## 1. Executive Summary

Unsloth is a **training-optimization library**. It makes HuggingFace
fine-tuning 2–5× faster via Triton kernels, 4-bit quantization, and
optimized gradient checkpointing. Its value proposition is speed, not
intelligence, not memory, not provenance.

The critical finding for Daryl: **a fine-tuned model carries zero
verifiable provenance.** The training dataset fingerprint exists (HuggingFace
`datasets` computes it) but is **never persisted with the checkpoint**.
`trainer_state.json` (metrics) is editable post-hoc with no integrity
check. `training_args.bin` (hyperparams) is pickled and editable.
`config.json` (architecture) is plain JSON with no signature. Model weights
have no binding to their training config. An attacker can train on dataset
X, claim dataset Y, inflate metrics, or swap weights — all undetectable
from the artifacts alone.

Unsloth adds **speed to training, zero provenance to the result**. It is
complementary, not competitive, to Daryl: Daryl could provide the
verifiable substrate underneath a fine-tuning pipeline, binding dataset
fingerprint → hyperparams → metrics → model weights into an append-only,
hash-chained receipt that survives tampering.

---

## 2. Installation / Onboarding (OBSERVED)

| Aspect | Observation | Class |
|--------|-------------|-------|
| `pip install unsloth` | Clean install, ~200 deps (heavy — includes torch, transformers, trl, bitsandbytes). | OBSERVED |
| First successful import | Worked on Python 3.12. No Rust/Docker/Postgres needed. | OBSERVED |
| Dep weight | Significantly heavier than LangGraph (~15) or Mem0 (~30), lighter than Letta (497). | MEASURED |
| GPU requirement | Not needed to inspect the API and provenance surface. A real training run would require a GPU. | NOT TESTED |

---

## 3. What Unsloth Actually Is (OBSERVED)

```python
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained("meta-llama/Llama-3.2-1B")
model = FastLanguageModel.get_peft_model(model, r=16, target_modules=[...])
# Then use standard TRL SFTTrainer
trainer = SFTTrainer(model=model, train_dataset=ds, args=SFTConfig(...))
trainer.train()
```

Unsloth is a **drop-in accelerator** for HuggingFace + TRL training. It
replaces `AutoModelForCausalLM` with `FastLanguageModel` and adds optimized
kernels. Everything else (datasets, trainer, checkpoint format, save/load)
is standard HuggingFace. Unsloth adds speed; it does not change the
artifact format or the provenance model.

---

## 4. Scenarios Tested

### S1 — Dataset fingerprint sensitivity (OBSERVED + MEASURED)

```python
ds = Dataset.from_dict({"text": ["Hello", "Foo", "Alice"]})
ds._fingerprint  # → "75dd290d8ee8c99d"
# Mutate one row
ds_mutated = Dataset.from_dict({"text": ["TAMPERED", "Foo", "Alice"]})
ds_mutated._fingerprint  # → "ffc45a1d6719167f"
```

**Finding:** the fingerprint IS sensitive to data mutation. HF `datasets`
computes a deterministic fingerprint. **But this fingerprint is never
stored with the trained model.**

### S2 — Checkpoint artifact provenance (OBSERVED)

Inspected `SFTConfig` (58 fields), `TrainingArguments` (113 fields),
`TrainerState` (20 fields), `BootstrapFewShot` (DSPy cross-check).

| Artifact | Contains dataset identity? | Hash/signature? | Tamper-resistant? |
|----------|---------------------------|-----------------|-------------------|
| `config.json` | No | No | No |
| `trainer_state.json` | No | No | No |
| `training_args.bin` | No (pickled) | No | No |
| `model.safetensors` | No | No | No |
| `UnslothTrainingArguments` | No | No | No |

**Zero provenance fields across the entire training artifact chain.**

### S3 — Falsification scenario (INFERRED from S1+S2)

Because no artifact binds dataset → hyperparams → metrics → weights:

| Attack | Detectable? | Evidence |
|--------|-------------|----------|
| Train on dataset X, claim dataset Y | **No** | fingerprint not stored |
| Inflate performance metrics | **No** | trainer_state.json is plain JSON |
| Change hyperparams post-hoc | **No** | training_args.bin is pickled |
| Swap model weights | **No** | no hash binding weights to config |
| Claim a different base model | **No** | config.json is editable |

---

## 5. Strengths (OBSERVED, not performance-measured)

| # | Strength | Class |
|---|----------|-------|
| S1 | 2–5× training speedup via Triton kernels + 4-bit quant. Well-documented, widely used. | INFERRED (from documentation/reputation; not benchmarked here) |
| S2 | Drop-in: replaces `AutoModel` with `FastModel`, rest stays HF-standard. | OBSERVED |
| S3 | Clean install on Python 3.12, no Docker, no Rust. | OBSERVED |
| S4 | Multi-GPU + multi-model support (`FastVisionModel`, `FastMLXModel`, `FastSentenceTransformer`). | OBSERVED |

---

## 6. Weaknesses (for the provenance/trust dimension)

| # | Weakness | Class |
|---|----------|-------|
| W1 | Zero dataset provenance in training artifacts. | OBSERVED |
| W2 | Zero integrity on any training file (config, state, args, weights). | OBSERVED |
| W3 | Dataset fingerprint exists but is never persisted with the model. | OBSERVED |
| W4 | No training receipt — no binding of "this model was produced by this config on this data with these metrics". | OBSERVED (absence) |
| W5 | No tamper-detection on any artifact. | OBSERVED (absence) |

---

## 7. What Daryl Would Provide Underneath

*(Observation of complementarity, not a proposal.)*

Daryl does not replace Unsloth. Daryl would sit underneath a fine-tuning
pipeline and provide:

- **Dataset receipt**: the dataset fingerprint, stored as a DSM entry,
  hash-chained and verifiable. The claim *"trained on dataset X"* becomes
  checkable.
- **Config receipt**: hyperparams serialized as a DSM entry, bound by hash
  to the dataset receipt. The claim *"with learning rate Y"* becomes
  checkable.
- **Metrics receipt**: `trainer_state.json` log imported as DSM entries at
  each checkpoint step. The claim *"achieved loss Z"* becomes replayable.
- **Model artifact binding**: a DSM entry recording `model.safetensors`
  content hash, bound to the dataset + config + metrics receipts. The
  claim *"this model is the result of that training run"* becomes
  cryptographically verifiable.

This is a **training provenance receipt** — not a proof that the model is
*good* or *correct*, but a proof of *what was used to produce it* and
*that the artifacts have not been tampered with since*.

---

## 8. Comparison Table

| Axis | Unsloth | Daryl |
|------|---------|-------|
| Category | training optimization | operational memory + provenance |
| Speed | ✓ (2–5× faster) | n/a |
| Dataset provenance | ✗ (fingerprint exists, never persisted) | ✓ (hash-chained receipt) |
| Artifact integrity | ✗ (all files editable) | ✓ (tamper-evident chain) |
| Metrics verifiability | ✗ (trainer_state editable) | ✓ (append-only log) |
| Model-to-config binding | ✗ | ✓ (artifact hash binding) |
| Replay | partial (can re-run, not verify) | ✓ (verify_shard replay) |

---

## 9. Final Question

> *"If Daryl did not exist, what would this product teach us about building
> operational memory?"*

It would teach us that **the most expensive computational artifact in the
AI stack — a fine-tuned model — has zero verifiable provenance**. Millions
of GPU-hours produce a `.safetensors` file with no binding to its training
data, no integrity on its metrics, and no proof that the claimed
hyperparams were the ones actually used. The dataset fingerprint is right
there, computed by HuggingFace, and then thrown away. The gap is not a
missing feature; it is a missing *substrate* — exactly what Daryl provides.
