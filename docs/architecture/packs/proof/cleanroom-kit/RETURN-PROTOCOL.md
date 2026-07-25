# Return protocol

## Your label

Use the label assigned to you when the kit was handed over. It goes in the `implementation` field of your
result file and in its filename: `results-<label>.json`. If no label was assigned, use `C` — `A` and `B` are
taken.

## What to return

A single archive containing exactly:

    results-<label>.json      your complete replay result, per spec/REPLAY-ENVELOPE.md
    ARCHITECTURE.md           your design, including the permutation-invariance argument
    AMBIGUITIES.md            every point the specification did not decide, and how you decided it
    COMMANDS.md               your command audit trail, written as you went
    <your source files>       the resolver and the replay harness
    ATTESTATION.md            see below

Nothing else. In particular, do not return the kit back.

## `ATTESTATION.md`

A short signed statement containing:

1. The sha256 of `KIT-MANIFEST.sha256` as you received it, and confirmation that `sha256sum -c
   KIT-MANIFEST.sha256` reported `OK` for every line.
2. A statement, in your own words, that you did not read, receive or infer any other implementation of this
   specification, and did not obtain any expected output or expected hash for these vectors, at any point
   before your result file was final.
3. The date and time (UTC) at which your result file was finalised, and its `v1:` hash — computed over its
   canonical bytes per `CANONICALISATION.md`. **Compute and record this hash before you send anything and
   before you receive anything back.** It is what makes "these were my results, before I saw yours" checkable
   rather than asserted.
4. Anything you consider a caveat on your own independence. An honest caveat costs nothing and a concealed
   one voids the whole exercise.

## What happens next

Your result file is compared against the first implementation's on **seven axes, separately**:

1. `resolved` / `refused` status;
2. the effective manifest, by value identity;
3. the resolution trace;
4. the refusals and their order;
5. `effective_manifest_hash`;
6. `refusal_hash`;
7. the referenced artifacts.

The acceptance criterion is: *for every vector and every admissible permutation of the inputs, the two
implementations either produce resolved results identical by value and by hash, or produce the same typed
refusal, with the same order and the same canonical hash.*

Every divergence is recorded **before** anything is corrected, and classified as one of: an ambiguity in the
ADR; an insufficiency in a schema; an incorrect or incomplete vector; an error in the first implementation; an
error in yours. **No expected output is regenerated automatically, and neither the ADR nor the vectors will be
edited to make either implementation pass.** Where the classification is "ambiguity in the ADR", the outcome
is a proposed amendment, and your `AMBIGUITIES.md` is the primary evidence for it.

A divergence traced to the specification is a success of this exercise, not a failure of your work.
