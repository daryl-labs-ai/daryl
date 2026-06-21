# Agent Memory Audit Report

## Query
- Decision hash: `v1:<hash>`
- Shard: `agent_memory`
- Depth: 2

## Decision
- Statement: Recommend replacing the board immediately.
- Entry hash: `v1:<hash>`
- Confidence: 0.8 (self-estimate, not calibrated)
- Depends on:
  - `v1:<hash>`
- Source refs:
  - none

## Supporting Facts
### Fact 1
- Statement: Downtime costs $50,000 per day.
- Entry hash: `v1:<hash>`
- Confidence: 1.0 (self-estimate, not calibrated)
- Depends on:
  - none
- Source refs:
  - none

## Hypotheses
### Hypothesis 1
- Statement: The used board can be sourced and installed quickly.
- Entry hash: `v1:<hash>`
- Confidence: 0.7 (self-estimate, not calibrated)
- Depends on:
  - none
- Source refs:
  - shard=`agent_memory` entry_hash=`v1:<hash>`

## Inferences
### Inference 1
- Statement: Immediate replacement is economically justified if service resumes within one day.
- Entry hash: `v1:<hash>`
- Confidence: 0.85 (self-estimate, not calibrated)
- Depends on:
  - `v1:<hash>`
  - `v1:<hash>`
- Source refs:
  - none

## Source References
- hypothesis `v1:<hash>` -> shard=`agent_memory` entry_hash=`v1:<hash>`

## Warnings
- None

## Verification
- Local status: OK
- Verification hint: `dsm verify --shard agent_memory`
- Scope: local tamper-evident; not external anchoring

## Trust Model / Limitations
- This report is local tamper-evident only.
- It does not prove factual truth.
- It does not prove reasoning validity.
- It does not replace `dsm verify`.
- It is not external anchoring.
- It includes no witness, MMR, STH, or anchoring mechanism.
