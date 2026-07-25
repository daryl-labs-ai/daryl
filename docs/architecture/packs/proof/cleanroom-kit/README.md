# Clean-room kit — Daryl pack resolver v0.1

**Purpose.** This kit contains everything, and only everything, needed to write an independent implementation
of the Daryl pack composition law and to replay a fixed set of input vectors against it. A first
implementation of this specification exists. **Nothing in this kit comes from it.** No source, no function
name, no output, no expected hash, no defect journal. That is the point: if an implementation written from
this kit alone agrees with the first one, hash for hash, the specification is reproducible by an independent
party; if it disagrees, the disagreement locates a hole in the specification, and that is a more valuable
result than agreement.

## What is in the kit

    README.md                            this file
    BRIEF.md                             what to build, what to deliver, what is forbidden
    CANONICALISATION.md                  the normative canonical-form and hash rules
    RETURN-PROTOCOL.md                   how to return your results
    KIT-MANIFEST.sha256                  sha256 of every file in the kit

    spec/ADR-PACK-0001-composition-and-precedence.md   THE LAW
    spec/ADR-PRL-0014-pack-context-referents.md        the context referents
    spec/pack.v0.1.schema.json                         the shape of a pack
    spec/pack-resolution.v0.1.schema.json              the shape of every output
    spec/REPLAY-ENVELOPE.md                            the result container (contains no resolution rule)

    inputs/resolution-vectors.INPUTS-ONLY.json         19 vectors, 20 pack documents, NO expected outputs
    inputs/examples/*.yaml                             five worked example packs
    inputs/compatibility-matrix.example.yaml           non-normative, NOT an input to resolution

## What is deliberately absent

- Any implementation of this specification, in any language, in whole or in part.
- Any expected output, expected manifest, expected refusal set or expected hash. The vector file records its
  own redaction: `"x-oracles-removed": {"vectors_expected": 19, "packs_content_hash": 20}`.
- Any test that would tell you whether you are right. You will not know. That is intended.

## Two disclosures, made rather than hidden

1. **`ADR-PACK-0001` states that a first implementation exists**, in its R9 rationale and its "Proof gate"
   section, and refers to a `tools/` directory that is not shipped here. That text is part of the ratified
   normative document and is delivered verbatim rather than edited: shipping a mutilated law would create a
   divergence risk larger than the one it removes. It describes no algorithm and reveals no result.
2. **The R9 rationale mentions that the two ordering vectors involve refusals whose `detail` fields sort
   against their paths.** This is a genuine partial hint about output shape, and it is disclosed here so that
   any later independence claim can account for it. It does not say what `detail` contains for any refusal
   code — see `BRIEF.md`, which asks you to report exactly that gap if you find it.

## How to verify what you received

    sha256sum -c KIT-MANIFEST.sha256

Every line must report `OK`. Quote the manifest's own sha256 in your return so that what you attest to having
received is fixed on the record.

## Start here

Read `BRIEF.md`, then `spec/ADR-PACK-0001-composition-and-precedence.md`, twice.
