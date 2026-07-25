# Replay envelope — the neutral container for a two-implementation replay

**Status:** Proposed · **Date:** 2026-07-25 · **Governs:** the A/B double replay of `resolution-vectors.v0.1.json`

This document defines **only a container**. It contains no resolution rule, no precedence, no merge
semantics, no refusal ordering. Every rule lives in `ADR-PACK-0001`; every shape lives in
`pack-resolution.v0.1.schema.json`. An implementation cannot learn anything about *how to resolve* from this
file, which is why both implementations may emit against it without that constituting a shared dependency.

## Why it exists

The acceptance criterion compares two implementations on seven axes separately. Comparing them requires one
agreed serialization of "what an implementation produced", or every difference becomes a difference of
reporting rather than of resolution. That is all this is.

## The unit: one `(vector, permutation)` replay

For every vector, for **every** permutation of its declared pack list, an implementation calls its own
`resolve(packs, evaluated_at, resolver_version)` and produces one **output envelope**:

```json
{
  "outcome": "resolved" | "refused",
  "effective_manifest":      { ... },      // resolved only, verbatim, per schema
  "effective_manifest_hash": "v1:<64hex>", // resolved only
  "resolution_trace":        { ... },      // resolved only, verbatim, per schema
  "trace_hash":              "v1:<64hex>", // resolved only
  "contested_paths":         [ "..." ],    // resolved only, sorted
  "phase":          "P1_identity" | ... ,  // refused only
  "refusals":       [ { ... } ],           // refused only — ARRAY ORDER IS SIGNIFICANT (R9)
  "refusal_codes":  [ "..." ],             // refused only, sorted, deduplicated
  "refusal_hash":   "v1:<64hex>",          // refused only — hash of the whole resolution_refusal object
  "artifacts":      [ { "role": "...", "ref": "...", "key": "v1:<64hex>" } ]
}
```

The envelope carries the **seven compared axes and nothing else**. The `PackResolutionReceipt` is
deliberately *not* in it: R13 defines the receipt as a pure projection of these same values, so comparing it
would compare nothing new — while forcing every implementation to decide what a receipt looks like for a pack
set refused *because* one of its layers is not a valid referent. That question belongs to a placement design,
not to a conformance replay.

The envelope carries **no permutation field, no timestamp of execution, no implementation name, no path, no
host**. It is a pure function of the vector, exactly like the resolution it reports. That is what makes the
next section possible.

### `artifacts`

The content-addressed keys this resolution produced or cited (R12), as a list sorted canonically by
`(role, ref, key)`:

| `role` | `ref` | `key` |
|---|---|---|
| `pack_content` | `pack_id@pack_version` | that pack's `content_hash` |
| `effective_manifest` | `""` | `effective_manifest_hash` — resolved only |
| `resolution_trace` | `""` | `trace_hash` — resolved only |
| `resolution_refusal` | `""` | `refusal_hash` — refused only |

A refused resolution still lists `pack_content` for every pack that reached the pack set. Packs rejected in
P1 for an unknown layer are still packs; they are listed.

## The file: one implementation's complete result

```json
{
  "schema_version": "replay-envelope.v0.1",
  "implementation": "A" | "B",
  "resolver_version": "pack-resolver@0.1.0",
  "vector_file": "resolution-vectors.v0.1.json",
  "vectors": [
    {
      "vector_id": "three-layer-baseline",
      "permutation_count": 6,
      "distinct_outputs": 1,
      "by_permutation": [
        {"order": ["fiduciaire.base@0.1.0", "..."], "output_hash": "v1:<64hex>"}
      ],
      "outputs": {"v1:<64hex>": { /* the envelope above */ }}
    }
  ]
}
```

`output_hash` is the `v1:` hash of the canonical form of the envelope. `outputs` is keyed by that hash, so an
envelope is stored once however many permutations produced it.

**`distinct_outputs` must be `1` for every vector.** This is permutation-invariance made a number rather than
a claim: any value above 1 means that implementation's output depended on the order its input arrived in, and
`by_permutation` says exactly which orders diverged. This check is *internal* to each implementation and must
be run before any comparison with the other one.

`by_permutation` is emitted in lexicographic order of `order`, so the file itself does not depend on the
order permutations were generated in.

## Canonicalisation

ADR-0002, unchanged: `json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
allow_nan=False).encode('utf-8')`, hash `'v1:' + sha256(...).hexdigest()`. No new hashing law. An
implementation that reproduces these hashes with its own canonicaliser has proven its canonicaliser too.
