# Seal of implementation B — emitted BEFORE any contact with implementation A

Sealed at (UTC): 2026-07-25T20:46:52Z

At the moment of sealing, implementation A had not been restored to the repository working
tree, `results-a.json` had not been reopened, and no expected output or expected hash from the
frozen vector file had been consulted. B was built and run only from `/tmp/implb/inputs/`.

## Canonical hash of B's complete result

    results-b.json  (canonical content)  v1:5588919f360e0fb06b2010faa6a568c71d477aeeaa6b347305a7f870e58aaeaa

## SHA-256 of the sealed files, as bytes on disk

    resolver_b.py          sha256:d86d7ea931e1e91d488bcfc41208c6781d20ec558b25f60558750c447dbe3299  (33877 bytes)
    replay_b.py            sha256:8d029c8bedc6e1facd70e456eb58f8966385e0818b272657dc3a6742978eef70  (3445 bytes)
    results-b.json         sha256:5588919f360e0fb06b2010faa6a568c71d477aeeaa6b347305a7f870e58aaeaa  (55169 bytes)
    DESIGN-JOURNAL.md      sha256:c515b7f75f7c4554bad1e96317e97f7e719bdacc1d84f47fb11d5ace845ea20d  (19295 bytes)
    BRIEF.md               sha256:4ba30526c8548186f8306b07a6e20b93f044bd934331881845cb2dd4a1c4e0e2  (5926 bytes)

## Per-vector output hashes (the seven compared axes, one envelope per vector)

| vector | permutations | distinct_outputs | envelope hash |
|---|---|---|---|
| three-layer-baseline | 6 | 1 | v1:1aad78cb7842a429b15d357e4e61ca95ed67fe3f9efb4cbdb2e095679145397f |
| three-layer-permuted | 6 | 1 | v1:1aad78cb7842a429b15d357e4e61ca95ed67fe3f9efb4cbdb2e095679145397f |
| same-pack-different-source-ref | 24 | 1 | v1:1aad78cb7842a429b15d357e4e61ca95ed67fe3f9efb4cbdb2e095679145397f |
| peer-union-commutes | 24 | 1 | v1:cb75e17c9a19447f546be5415e9c75c08cd22f80d2cc17c319f4d6521b60399b |
| derogation-valid | 2 | 1 | v1:2ee107dea6f59e50ac9e429d254716508508cd63db3376d56b86cef1c7dc8620 |
| empty-packset | 1 | 1 | v1:1761569643700ec76d641b95e35861499e395f28e5b1391bb208666f9801a902 |
| peer-conflict-replace | 6 | 1 | v1:457324c41b9d9535df29a3777a1e9688084e3c9cd8073878762684d28a9a4665 |
| forbidden-override | 2 | 1 | v1:3b631b8b0d6e12da426a27b756b0ae0296d88da0b3a64b4f0692ca04b3649709 |
| derogation-required | 2 | 1 | v1:cb06f4008bdfa080b276badb7d6963aa346db88cdeb5bd3c8ec807e58f7ad8b5 |
| derogation-expired | 2 | 1 | v1:e6783c530f1b08d796bf2ce150ebc308970a0f05003e8d86be6edf09224a80ef |
| derogation-malformed | 2 | 1 | v1:908d320ed3a798bea49ffaa34d9acabd5014e9b3da46054ede126dc0f236911f |
| strategy-relaxation-refused | 2 | 1 | v1:f8205fdb2f2af25b711033d0f813ba87034daa4d03296251e7cb3a9db273d5bc |
| merge-semantics-conflict | 2 | 1 | v1:f3e6f9d41e5b793b2fce5b72fcc6ead8b367b0b0e5803f7cb63f27d6925efddb |
| undeclared-control-fails-closed | 2 | 1 | v1:bd2116eb47f6507696244a8ee0acae028dd3e91adaf02b0e58c34fb2dacc29db |
| unknown-referent-layer | 2 | 1 | v1:6fc244826d113772099fd207d042522bb69a9bbb877b101d5194214777d2f756 |
| duplicate-pack-identity | 6 | 1 | v1:f3a8577f5f267049ab2ec443e69ef7ed74eb56a2e22fb39c49e8c49b0608d9a8 |
| compatibility-violation | 2 | 1 | v1:243751ab61e0eb12fa5564addcbfb47bb2bc09ec6d0e476e16a132b22bb2ef5c |
| refusal-ordering-by-path | 6 | 1 | v1:c052a5cdb575a88855d9d759d94f14f5e90006d41b80735913b16c9f21360734 |
| refusal-ordering-tie-break | 2 | 1 | v1:11a7865895f0e0a859c71afef16e12acff2873a6352c9d9eaa52946495cf6f50 |

Total: 19 vectors, 101 permutations, distinct_outputs == 1 everywhere.
