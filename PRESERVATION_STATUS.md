# DARYL Packs v0.1 — Partial Historical Preservation

Status: INCOMPLETE HISTORICAL PRESERVATION

This branch exists to stop two authentic commits from being lost. It is not a
milestone, not a deliverable, and not a claim that Packs v0.1 is preserved.

Preserved historical commits:
- a17a89c3ca9be6be45f60e3df7ac215851068860
- 17296ef46ca433199e24752d0ecd236d43f4ba52

Missing historical commit:
- c469107... — LOST. No durable copy is known to exist.

Preserved patch SHA-256:
- 0001: 0be76b555f4e506df8307b0ba4191f80c732a36a0a46c31385bb6cbc3ad6ba12
- 0002: 966e67f51a9bf14993fb9beec0ea5ebcec2e8811ad0255fc11a76a1445f5c42a

Missing original patch SHA-256:
- 0003: 3c971b0e400c64d5b122b1f14c6d80164f7eec4047c4ac8a167d31112a69ecaa

Both preserved patches were verified against the SHA-256 values above before
application, and each patch's `From` header names the historical commit it was
generated from.

## What this branch is not

- This branch is NOT the complete DARYL Packs v0.1 lot.
- This branch is NOT ratified.
- This branch MUST NOT be represented as `feat/daryl-packs-contracts-v0.1`.
- This branch MUST NOT be merged as the complete Packs v0.1 milestone.
- The missing third commit MUST NOT be reconstructed from secondary artifacts.
- Q7 remains blocking.
- ADR-PACK-0001 remains Proposed.
- ADR-PRL-0014 remains Proposed.
- No capability promotion is implied by this preservation branch.

## Commit identity: authors preserved, SHAs necessarily differ

The two commits on this branch do **not** carry the historical SHAs
`a17a89c...` and `17296ef...`. This is expected and is not a defect in the
patches.

A commit's SHA is computed over its tree, parent, author, **committer**, and
message. `git format-patch` records the author but does **not** record the
committer. Applying the patches with `git am` therefore preserves the original
author identity and authored dates byte-exactly, while the committer line is
necessarily rewritten to whoever replayed the patch, at the time they replayed
it.

The consequence is worth stating plainly: **byte-exact reproduction of the
historical commit SHAs is impossible from these patch files alone**, because
the committer metadata that fed the original hashes is not contained in them.
What is preserved is the content and the authorship, not the original commit
object identity.

Do not "repair" this by forging committer metadata to make the SHAs match. A
fabricated committer line would produce a commit that looks historical and is
not.

## Content coverage of what is preserved

The two preserved commits contribute 62 files and 26,511 insertions, entirely
under `docs/architecture/packs/`. No file under `src/` is touched, and the
frozen kernel at `src/dsm/core/` is unchanged — consistent with both commit
messages, which describe the work as documentary.

The historical lot was recorded as roughly 75 files and ~28,896 insertions. The
shortfall of roughly 13 files and ~2,385 insertions corresponds to the missing
third commit. That gap is a fact about this branch and must not be closed by
regenerating plausible content.

## On secondary artifacts

Secondary artifacts from the original work — session reports, audit notes,
conversation transcripts, review summaries, diffstat tables — may still be
useful for understanding *what the third commit was about*, what it claimed,
and why it mattered.

They are **not** a sufficient source to recreate it. They describe the work;
they do not contain it. Anything regenerated from them would be new content
wearing a historical label: it would carry a different tree, it could not be
checked against `3c971b0e...`, and it would silently convert an honest gap into
a false record.

If a durable copy of patch `0003` (SHA-256 `3c971b0e400c64d5b122b1f14c6d80164f7eec4047c4ac8a167d31112a69ecaa`)
is ever recovered, it can be applied on top of this branch and verified against
that hash. Until then, the third commit stays missing, and this note stays.
