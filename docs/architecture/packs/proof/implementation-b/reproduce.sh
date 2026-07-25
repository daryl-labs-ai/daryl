#!/bin/sh
# Rebuilds implementation B's result file from source, in a scratch directory, and checks it against
# the recorded sha256. Reads nothing from A and nothing from resolution-vectors.v0.1.json.
#
#   sh reproduce.sh sealed     B exactly as sealed, before it had seen anything of A
#   sh reproduce.sh r2         B after its one genuine defect (D1) was corrected
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
VARIANT=${1:-sealed}
case "$VARIANT" in
  sealed) WANT=5588919f360e0fb06b2010faa6a568c71d477aeeaa6b347305a7f870e58aaeaa ;;
  r2)     WANT=eff8a7bb22f66691ea4c5366d29c87dd560180986ea3ae2860e9814885de3794 ;;
  *) echo "usage: reproduce.sh [sealed|r2]" >&2; exit 2 ;;
esac
WORK=$(mktemp -d)
cp "$HERE/$VARIANT/resolver_b.py" "$HERE/$VARIANT/replay_b.py" "$WORK/"
mkdir -p "$WORK/inputs"
cp "$HERE/inputs/resolution-vectors.INPUTS-ONLY.json" "$WORK/inputs/"
(cd "$WORK" && python3 replay_b.py | tail -2)
GOT=$(sha256sum "$WORK/results-b.json" | cut -d' ' -f1)
echo "rebuilt  $GOT"
echo "recorded $WANT"
if [ "$GOT" = "$WANT" ]; then
  cmp "$WORK/results-b.json" "$HERE/$VARIANT/results-b.json" && echo "REPRODUCED — byte-identical"
else
  echo "DIVERGED — the recorded result is not reproducible from this source" >&2
  rm -rf "$WORK"; exit 1
fi
rm -rf "$WORK"
