# Command audit trail — implementation B

Every command run inside `/tmp/implb` while B was being written, in order. This exists to support the
independence claim: it shows what was read and when, and that nothing outside `/tmp/implb/inputs/` was opened
before B was sealed.

## Sandbox preparation (before B started)

    mkdir -p /tmp/implb/inputs/examples
      # the isolated workspace for B

    cp <ADRs, schemas, examples, compatibility matrix> /tmp/implb/inputs/
      # the admissible inputs, copied in before the workspace was sealed

    python3 - <<'PY' ... PY
      # produced inputs/resolution-vectors.INPUTS-ONLY.json by stripping, from the frozen vector file,
      # all 19 per-vector `expected` blocks and all 20 per-pack `content_hash` values.
      # Recorded in the file itself as: "x-oracles-removed": {"vectors_expected": 19, "packs_content_hash": 20}

    mv <tools/, proof/, resolution-vectors.v0.1.json> /tmp/quarantine_A/
      # implementation A, its replay harness and the frozen oracle removed from the repository working tree

    find /tmp/daryl -name '*.py' -path '*packs*' | wc -l
      # -> 0 : verification that no implementation source remained reachable in the repository tree

## Writing B

    (Read)  /tmp/implb/inputs/ADR-PACK-0001-composition-and-precedence.md
    (Read)  /tmp/implb/inputs/ADR-PRL-0014-pack-context-referents.md
    (Read)  /tmp/implb/inputs/pack.v0.1.schema.json
    (Read)  /tmp/implb/inputs/pack-resolution.v0.1.schema.json
    (Read)  /tmp/implb/inputs/REPLAY-ENVELOPE.md
    (Read)  /tmp/implb/inputs/compatibility-matrix.example.yaml
    (Read)  /tmp/implb/inputs/examples/*.yaml
      # the law, the shapes, the container, the worked material

    cd /tmp/implb && python3 -c "import json; d=json.load(open('inputs/resolution-vectors.INPUTS-ONLY.json')); ..."
      # dumped the vector file's structure, its 20 pack documents and its `why` prose.
      # No `expected` block exists in that file to dump.

    (Write) /tmp/implb/DESIGN-JOURNAL.md
      # opened the append-only design journal; entries E01-E14 recorded BEFORE any code was written

    (Write) /tmp/implb/resolver_b.py
    (Write) /tmp/implb/replay_b.py

## Running B

    cd /tmp/implb && python3 replay_b.py
      # first complete run: 19 vectors, 101 permutations, distinct_outputs == 1 everywhere, exit 0

    cd /tmp/implb && python3 -c "... dump refusals of the ordering vectors ..."
      # self-review of B's own output; no oracle consulted

    (Edit) /tmp/implb/resolver_b.py   x4
      # aligned the `detail` policy in the code with the rule recorded in the journal (E15):
      # removed `detail` from unknown_referent, duplicate_pack_identity, merge_semantics_conflict,
      # strategy_relaxation_refused and peer_conflict

    cd /tmp/implb && python3 replay_b.py
      # re-run after the correction: same 19/101, distinct_outputs == 1 everywhere, exit 0

    (append) /tmp/implb/DESIGN-JOURNAL.md
      # entries E15-E18

## Sealing B

    cd /tmp/implb && python3 - <<'PY' ... PY
      # wrote SEAL-B.md: UTC timestamp, canonical hash of results-b.json, sha256 of each sealed file,
      # per-vector envelope hashes. Executed BEFORE implementation A was restored or consulted.

    (Write) /tmp/implb/ARCHITECTURE.md
    (Write) /tmp/implb/COMMANDS.md

## What was NOT run

No command read, listed, grepped or opened anything under `/tmp/quarantine_A`, `/tmp/out`, `/root/.claude`, or
`docs/architecture/packs/tools/` while B was being written. No web search was performed. No Daryl module was
imported by `resolver_b.py` — the canonicalisation and the hash are implemented from the ADR-0002 formula with
`json` and `hashlib`.

## Honest limitation

This container runs as root, so no permission scheme could make the quarantine a hard barrier. The guarantee
offered here is **absence-by-path plus an audit trail**, not sandbox enforcement. The stronger guarantee —
that the author of B never held A in mind — is not available in this session at all, and is exactly what the
clean-room kit exists to obtain from a third party.
