#!/bin/sh
# Rebuilds the clean-room kit tarball reproducibly from this directory.
# Deterministic: sorted entries, fixed mtime, numeric owner 0:0. Same input tree -> same sha256.
#
#   sh build-tarball.sh [output-dir]     default: current directory
#
# Expected: daryl-pack-resolver-cleanroom-v0.1.tar.gz, 34549 bytes, sha256
#   c60b0b1e69305f10b7a87800050344bf653ea297a7cbe5a54c330dbf5b831281
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-$(pwd)}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
STAGE=$(mktemp -d)
mkdir -p "$STAGE/daryl-pack-resolver-cleanroom-v0.1"
(cd "$HERE" && tar -cf - --exclude build-tarball.sh --exclude TARBALL.sha256 .) \
  | (cd "$STAGE/daryl-pack-resolver-cleanroom-v0.1" && tar -xf -)
(cd "$STAGE/daryl-pack-resolver-cleanroom-v0.1" && sha256sum -c KIT-MANIFEST.sha256 >/dev/null)
(cd "$STAGE" && tar --sort=name --mtime='2026-07-25T00:00:00Z' --owner=0 --group=0 \
   --numeric-owner -czf "$OUT/daryl-pack-resolver-cleanroom-v0.1.tar.gz" \
   daryl-pack-resolver-cleanroom-v0.1)
rm -rf "$STAGE"
sha256sum "$OUT/daryl-pack-resolver-cleanroom-v0.1.tar.gz"
