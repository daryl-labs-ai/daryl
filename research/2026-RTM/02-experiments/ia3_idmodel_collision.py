#!/usr/bin/env python3
"""Inter-Agent 3 — Identity collision via IdentityRegistry (v0.8.0 pillar A)."""
from __future__ import annotations
import shutil, sys, tempfile, json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "packages" / "dsm-primitives" / "src"))

from dsm.core.storage import Storage
from dsm.identity.identity_registry import IdentityRegistry


def main():
    tmp = Path(tempfile.mkdtemp(prefix="ia3_"))
    try:
        storage = Storage(data_dir=str(tmp))
        reg = IdentityRegistry(storage=storage)

        print("=== T1: RÉENREGISTREMENT agent_X (alice puis mallory) ===")
        # alice registers agent_X
        reg.register(agent_id="agent_X", public_key="pk_alice_001",
                     owner_id="alice", owner_signature="sig_alice",
                     model="gpt-4")
        resolved_alice = reg.resolve("agent_X")
        print(f"  alice enregistre agent_X: owner={resolved_alice.owner_id}, model={resolved_alice.model}")
        # mallory re-registers agent_X with own key/owner
        reg.register(agent_id="agent_X", public_key="pk_mallory_EVIL",
                     owner_id="mallory", owner_signature="sig_mallory",
                     model="claude-3")
        resolved_mallory = reg.resolve("agent_X")
        print(f"  mallory réenregistre agent_X: owner={resolved_mallory.owner_id}, model={resolved_mallory.model}, pk={resolved_mallory.public_key}")
        if resolved_mallory.owner_id == "mallory":
            print(f"  → resolve('agent_X') retourne maintenant mallory (latest-wins)")
            print(f"    Forgery d'identité SILENCIEUX — aucune erreur levée")
            print(f"    Classification: TRUST_GAP (forgery possible, trace conservée)")
        print()

        print("=== T2: DEUX AGENTS, MÊME MODEL_ID ===")
        reg.register(agent_id="agent_Y", public_key="pk_bob_001",
                     owner_id="bob", owner_signature="sig_bob", model="gpt-4")
        reg.invalidate = lambda: None  # noop
        # force rebuild
        reg._index = None
        rx = reg.resolve("agent_X")
        ry = reg.resolve("agent_Y")
        print(f"  agent_X: owner={rx.owner_id} model={rx.model}")
        print(f"  agent_Y: owner={ry.owner_id} model={ry.model}")
        distinct = rx.agent_id != ry.agent_id
        same_model = rx.model == ry.model
        if distinct and same_model:
            print(f"  → Même model, agents DISTINCTS: DSM distingue agent_id du model_id (SAFE)")
        print()

        print("=== T3: TRACE HISTORIQUE (audit replay) ===")
        all_entries = storage.read("identity_registry", limit=1000)
        x_regs = []
        for e in all_entries:
            try:
                c = json.loads(e.content)
                if c.get("agent_id") == "agent_X" and c.get("event_type") == "register":
                    x_regs.append((c.get("owner_id"), c.get("public_key"), e.timestamp.isoformat()[:19]))
            except Exception:
                pass
        print(f"  Historique register de agent_X: {len(x_regs)} events")
        for owner, pk, ts in x_regs:
            print(f"    {ts} owner={owner} pk={pk[:20]}...")
        if len(x_regs) >= 2 and x_regs[0][0] != x_regs[-1][0]:
            print(f"  → History append-only PRÉSERVE la trace d'alice (audit-safe)")
            print(f"    MAIS resolve() retourne mallory (latest-wins écrase)")
            print(f"    → Gap: résolution runtime ≠ trace audit")
        print()

        print("=== T4: REVOCATION — qui peut révoquer? ===")
        # After forgery, agent_X owner is mallory. Can alice revoke?
        try:
            reg._index = None
            reg.revoke(agent_id="agent_X", owner_id="alice",
                       owner_signature="sig_alice", reason="reclaim")
            print(f"  alice révoque agent_X: ok — alice peut reprendre le contrôle")
            print(f"    → revoke() vérifie l'owner COURANT (mallory), pas l'original")
            resolved_after = reg.resolve("agent_X")
            print(f"    resolve après revoke: {resolved_after}")
        except Exception as e:
            print(f"  alice révoque agent_X: échec — {type(e).__name__}: {e}")
            print(f"    → revoke() exige owner_id == owner courant (mallory)")
            print(f"    → alice a perdu le contrôle: forgery irréversible sans admin")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
