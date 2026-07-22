"""DSM Swarm benchmark harness — typed contracts (B1).

Benchmark-side only: NOTHING here is product surface. The harness lives under
``benchmarks/`` (outside src/, kernel, writer allowlist and replay core).
Modules in this package import ``prl.swarm`` for cross-validation of fixtures
against the canonical models; they never import ``dsm.core.storage`` — any
future swarm write goes through ``PRLStore.commit_swarm_entry`` only (B2).
"""
