#!/usr/bin/env python3
"""Découverte 1 — Falsifier la stabilité datetime -> isoformat du hash canonique.

Hypothèse à falsifier: pour tout timestamp émis par le chemin d'écriture DSM
(datetime.now(timezone.utc).isoformat()), on a
    datetime.fromisoformat(x).isoformat() == x
et donc verify() == True sur un entry légitime.

Stratégie de falsification:
  1. Générer le spectre de datetimes que DSM peut produire (now UTC, diverses
     microsecondes, fold, naive vs aware, epoch extrêmes).
  2. Pour chaque datetime d, simuler write puis verify:
       x = d.isoformat()                         # ce qui est écrit sur disque
       d2 = datetime.fromisoformat(x)            # ce que verify reconstruit
       x2 = d2.isoformat()                       # ce que verify re-hash
       stable = (x == x2)
  3. Pour chaque cas INSTABLE, vérifier l'impact réel:
       build hash sur l'entry "écrit" (timestamp=x)  vs  "reconstruit" (timestamp=x2)
       Si les hashes diffèrent => un entry légitime est marqué TAMPERED.

AUCUNE modification du kernel. Lecture seule des primitives.
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone, timedelta

REPO = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))
from dsm_primitives import hash_canonical   # noqa


def entry_dict(timestamp_str: str, prev_hash=None) -> dict:
    """Forme canonique d'entry (per _build_canonical_entry)."""
    return {
        "session_id": "s1", "source": "agent",
        "timestamp": timestamp_str,
        "metadata": {}, "content": "hello", "prev_hash": prev_hash,
    }


def try_dt(d, label):
    """Retourne (stable: bool, written_ts, reconstructed_ts, h_written, h_reconstructed)."""
    x = d.isoformat()
    try:
        d2 = datetime.fromisoformat(x)
    except Exception as e:
        return (False, x, f"<fromisoformat error: {e}>", None, None)
    x2 = d2.isoformat()
    h_w = hash_canonical(entry_dict(x))
    h_r = hash_canonical(entry_dict(x2))
    return (x == x2 and h_w == h_r, x, x2, h_w, h_r)


cases = []

# (A) Le cas nominal: ce que DSM émet en pratique (now UTC avec µs)
for i in range(0, 10):
    cases.append((datetime.now(timezone.utc), f"now-utc-mu#{i}"))

# (B) Seconde pile (µs = 0) — frontière
for sec in (0, 30, 59):
    cases.append((datetime(2026, 3, 1, 12, 30, sec, 0, tzinfo=timezone.utc), f"exact-second-{sec}"))

# (C) Fold (Python-specific, possible via internal construction)
d_fold = datetime(2026, 3, 1, 12, 0, 0, fold=1, tzinfo=timezone.utc)
cases.append((d_fold, "fold=1"))

# (D) Datetime naïf (sans tzinfo) — DSM le tolère-t-il?
cases.append((datetime(2026, 3, 1, 12, 0, 0), "naive-no-tz"))

# (E) Offset non-UTC (le hash devrait être indépendant, mais isoformat diffère)
from datetime import timezone as _tz
cases.append((datetime(2026, 3, 1, 12, 0, 0, tzinfo=_tz(timedelta(hours=5, minutes=30))), "offset+0530"))

# (F) Microsecondes non nulles avec offset non-UTC (combinaison)
cases.append((datetime(2026, 3, 1, 12, 0, 0, 123456, tzinfo=_tz(timedelta(hours=-8))), "offset-08+mu"))

# (G) Extrêmes temporels
cases.append((datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc), "epoch"))
cases.append((datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc), "max"))


print(f"{'label':24} | {'stable':6} | {'written_ts':40} | {'reconstructed_ts':40}")
print("-" * 120)
failures = []
for d, label in cases:
    stable, x, x2, _, _ = try_dt(d, label)
    flag = "OK" if stable else "FAIL"
    print(f"{label:24} | {flag:6} | {str(x):40} | {str(x2):40}")
    if not stable:
        failures.append((label, x, x2))

print()
if failures:
    print(f"=== {len(failures)} CAS INSTABLES — impact hash canonique ===")
    for label, x, x2 in failures:
        h_w = hash_canonical(entry_dict(x))
        h_r = hash_canonical(entry_dict(x2))
        print(f"  [{label}]")
        print(f"     écrit       ts={x!r}")
        print(f"     reconstruit ts={x2!r}")
        print(f"     hash écrit       = {h_w}")
        print(f"     hash reconstruit = {h_r}")
        print(f"     DIVERGENCE HASH  = {h_w != h_r}  => verify() retournerait {'TAMPERED' if h_w != h_r else 'OK'}")
else:
    print("=== Tous les cas sont stables — hypothèse non falsifiée sur ce spectre ===")
