# B5 — Live Smoke Execution Plan (frozen BEFORE any live call)

Status: prepared, **NOT authorized**. `live_execution_authorized=false` in
`B5_SMOKE_CONFIG.json`. This plan freezes every execution decision before any
live data exists. Purpose of the smoke: **protocol feasibility**, not any
general claim about DSM (see `INTERPRETATION.md`).

## 1. Scope

One case (`c01-nominal`), one seed (0), three paired conditions A / B′ / B,
same provider, same model, same business prompts, same orchestration —
instrumentation as the only *intended* experimental variable
(`PARITY_SPEC_V0_1.md §1`).

**Why c01-nominal:** 8 steps, 4 roles, 5 agent-role provider calls per
condition — enough structure for parity to be observable; no exotic
diagnostic; not chosen to favor DSM (it plants NO fault, so B cannot "win" by
detection — the smoke can only measure feasibility, parity and overhead).
A single pair deliberately cannot test H1–H4 conclusively and the report will
not claim it does.

## 2. Frozen parameters (config: `B5_SMOKE_CONFIG.json`)

| Parameter | Value | Note |
|---|---|---|
| provider | `openai` | only SDK factually present in the canonical venv (`openai 2.44.0`, declared by the repo's `agents` extra); anthropic SDK absent |
| model | `gpt-5-mini` (proposed) | small/cheap tier; **final id + price frozen at authorization** |
| temperature | 0.0 | determinism best-effort |
| request_seed | 7 | best-effort; per-call honoring recorded in provenance |
| max_output_tokens_per_call | 512 | hard, provider-enforced |
| timeout / retry | 60 s; ≤2 retries, 2 s backoff | a call failing after retries ⇒ run INVALID (never low-scored) |
| price table | 5.0 / 20.0 USD per Mtok | **conservative placeholder ceiling** — to be replaced by the provider's actual published prices at authorization; caps hold regardless |
| caps | ≤ 10 USD · ≤ 200 000 tokens · ≤ 900 s · ≤ 30 calls | enforced BEFORE each call (`BudgetGuard.precheck`) |
| prompts | `prompts.py` @ this branch; block `grounding-block.v0.1` | three-level hashes recorded per step |
| corpus | `cases/01_c01-nominal.json` @ this branch | untouched since B4 |

## 3. Execution sequence (after authorization ONLY)

1. Preflight: repo on the approved SHA, gates green, `runs/` clean of any
   same-id directory.
2. Verify the authorization chain: config `live_execution_authorized=true`,
   explicit `authorized_budget_usd`, CLI `--live --i-authorize-live-spend`,
   `OPENAI_API_KEY` present (checked by NAME; value never read outside the
   transport).
3. Create the unique run dir `benchmarks/swarm/runs/b5-smoke-<utc-stamp>/`.
4. Run paired conditions in the order **A → B′ → B**, one shared BudgetGuard.
5. Collect raw artifacts per condition (manifest, event log, raw provider
   calls, receipts, prompt records, projection+verify for B′/B).
6. Validate every run (`verify == OK` + replay = validity condition).
7. Compute family E (behavioral parity) BEFORE any interpretation.
8. Classify each pair: `eligible` | `confounded — behavioral shift` |
   `invalid`. A confounded or invalid pair can NEVER support H1–H4.
9. Report per condition and per pair (`smoke_report.json`); aggregates none —
   a single pair has nothing to aggregate.

## 4. Order effect and mitigation

Order A → B′ → B is fixed (not randomizable with one pair). Known biases and
mitigations:

- **Provider-side prompt caching**: identical base prompts may be cached
  after A, cheapening/faster-ing B′/B inputs. Mitigation: no cache-control
  requested; cache-reported token fields (if returned) recorded per call;
  latency comparisons across conditions are DESCRIPTIVE ONLY in the smoke;
  cost comparison uses token counts, with any provider-reported cached-token
  field surfaced, not silently netted.
- **Temporal drift / load**: timestamps recorded per call; a single pair
  supports no latency claim anyway.
- **Rate limits**: retry policy above; a retry storm crossing caps aborts
  (bounded failure = data, reported as such).

Residual order effects are listed as validity threats in the smoke report —
never absorbed.

## 5. STOP conditions (immediate, mid-run)

Cost or token cap would be crossed by the next call (precheck) · global
timeout · unexpected provider error after retries · prompt hash mismatch
(G2 recomposition violated) · invalid manifest · any write outside
`PRLStore.commit_swarm_entry` · secret material detected in any artifact ·
unverifiable run (`verify != OK`). On STOP: artifacts persisted as-is,
`smoke_report.json` carries `aborted`, nothing is retried beyond policy,
nothing is deleted.

## 6. The exact command (after authorization)

```bash
PYTHONPATH=. .venv/bin/python -m benchmarks.swarm.harness.smoke \
  --config benchmarks/swarm/B5_SMOKE_CONFIG.json \
  --out benchmarks/swarm/runs/b5-smoke-$(date -u +%Y%m%dT%H%M%SZ) \
  --live --i-authorize-live-spend
```

Refused today on THREE independent grounds: the config's
`live_execution_authorized=false`, the absent authorized budget, and the
absent `OPENAI_API_KEY`. The dry-run form (drop `--live
--i-authorize-live-spend`) is runnable now at zero cost and zero network.

## 7. What the smoke may conclude — and may not

May: the live protocol is executable end-to-end within caps; parity
measurement works on live traffic; overhead is measurable; validity gates
fire correctly. May NOT: any support for H1–H4 (one pair, nominal case), any
truth/intelligence/hallucination claim, any generalization beyond this case,
model and day.
