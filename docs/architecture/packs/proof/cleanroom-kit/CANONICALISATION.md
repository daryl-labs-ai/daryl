# Canonicalisation and hashing — normative

These rules are normative and unchanged from ADR-0002. They are restated here so that the kit is
self-contained; `spec/ADR-PACK-0001-composition-and-precedence.md` and `spec/REPLAY-ENVELOPE.md` state the
same thing, and if they differ from this page, they govern.

## Canonical bytes

```python
canonical = json.dumps(
    data,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
    allow_nan=False,
).encode("utf-8")
```

In another language, produce byte-for-byte the same result: object keys sorted by their Unicode code points,
no whitespace anywhere, `,` and `:` as the only separators, every non-ASCII character escaped as `\uXXXX`,
and `NaN`/`Infinity`/`-Infinity` rejected rather than emitted.

## Hash

```python
digest = "v1:" + hashlib.sha256(canonical).hexdigest()
```

Lower-case hex, 64 characters, prefixed `v1:`. A verifier fails closed on any prefix it does not know: an
unrecognised prefix is a refusal, never a fallback to "assume sha256".

## Where it applies

Every `v1:` hash in this specification is the hash of the canonical bytes of a JSON value:

- a pack's `content_hash` — over the pack document, transformed as `ADR-PACK-0001 R12` directs;
- `effective_manifest_hash` — over the whole effective manifest object;
- `trace_hash` — over the whole resolution trace object;
- `refusal_hash` — over the whole resolution refusal object;
- `output_hash` in the replay file — over the whole output envelope.

## Value identity

Wherever the law says two values are "identical", the test is equality of their canonical bytes. This matters
in at least three places — peer agreement, the derivation of `selected_from`, and any deduplication you
perform — and using a language-native `==` instead will eventually disagree with it (`1` versus `1.0`, key
order, integer versus float, string normalisation).

## Reproducing these hashes is itself a result

An implementation that reproduces another's hashes with its own canonicaliser has proven its canonicaliser
too. There is no separate canonicalisation conformance suite, and none is needed.
