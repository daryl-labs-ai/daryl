# SECURITY_AND_PROVENANCE

## Secret scan — payload

Scanned for Anthropic/OpenAI keys, Slack and GitHub tokens, AWS access keys, private
key blocks, hardcoded passwords, cookies, private endpoints, the user's email address,
the user's username, machine identifiers and local temp paths.

| Category | Result |
|---|---|
| API keys / tokens / private keys | **none** |
| hardcoded passwords or cookies | **none** |
| absolute home paths (`/Users/...`) | **none** |
| user email / username | **none** |
| machine temp paths (`/var/folders/...`) | **none** |
| binaries, model files, large fixtures | **none** |
| non-stdlib runtime imports | **none** |

No secret value is reproduced in this report, per §24.

## Findings that were remediated rather than accepted

**Absolute local path.** `research/hexashard_adapter_v01/fixtures/CORE_MANIFEST.json`
carried `core_root: /Users/<user>/Documents/DARYL/...`. The file was **excluded**; its
purpose is served by the digests embedded in `core_lock.py`, which need no path.

**Unvalidated URL scheme.** See F-06 in INDEPENDENT_FINDINGS.md. `config.endpoint` went
straight to `urlopen`, which honours `file:`. Fixed with an `http`/`https` allowlist.
This also cleared DARYL's `bandit -r src/ -ll` gate, which the payload was failing.

## Where credentials are handled

The live-experiment harness reads `ANTHROPIC_API_KEY` from the environment or the
macOS keychain and never writes it anywhere. That harness is **not migrated** — it
stays in the research tree. The migrated Adapter has **no credential handling at all**:
its only network provider is a local Ollama endpoint with no auth.

## Excluded because it contains machine-local data

`research/hexashard_live_llm_001/raw/` and `research/hexashard_live_llm_001_local/raw/`
hold raw provider call logs and `/var/folders/...` checkpoint paths. Summarised in
EVIDENCE.md, not shipped.

## Provenance and licence

- **No third-party code is vendored.** Core and Adapter are original, standard library
  only. There are no copied snippets, generated files or vendored dependencies.
- **No new runtime dependency** is introduced, so no new licence obligation is either.
- The payload inherits the repository's existing `LICENSE`.
- Nothing here requires attribution to an external project.

## Public-claim review

Draft documentation was written against the measured evidence and deliberately does
**not** claim infinite context, hallucination prevention, any universal token-saving
multiple, better model intelligence, semantic retrieval, or a spatial-retrieval
advantage. Both context-reduction figures (31.7x, ~280x) are stated as properties of
the specific fixture that produced them. LIVE 001 is described as inconclusive and is
cited in support of nothing.
