"""R-consult v1 (ADR-PRL-0008) — kernel-backed tests: commit a consultation act via
PRLStore (Storage.append, certified chain) and read it back through RR by action_name.

Requires the real DSM kernel (dsm.core.storage / dsm.verify / dsm.rr) — same as
test_dsm_store.py and test_structural.py. No new writer is introduced: the act is
written through the already-registered prl/store module.
"""

from __future__ import annotations

from dsm.core.storage import Storage
from dsm.rr.index import RRIndexBuilder
from dsm.rr.navigator import RRNavigator
from dsm.verify import verify_shard

from prl.collectors import ConsultationAdapter, make_resolution
from prl.store import CONSULTATION_SHARD, ActResult, PRLStore
from prl.types import Carrier, ConsultationNode, from_entry


def _store(tmp_path) -> PRLStore:
    return PRLStore(Storage(data_dir=str(tmp_path)))


def _act():
    return ConsultationAdapter().to_act(
        subject_id="ko-42", answer="use chunk_primary", producer="claude via adapter v1",
        agent_id="agent.test", confidence=0.7,
    )


# --- commit_act: certified, in the consultation shard, no new writer --------

def test_commit_act_certifies(tmp_path):
    store = _store(tmp_path)
    res = store.commit_act(_act())
    assert isinstance(res, ActResult)
    assert res.shard == CONSULTATION_SHARD
    assert res.act_id and res.tip_hash  # certification = chain tip hash
    report = verify_shard(store._storage, res.shard)
    assert str(report["status"]).endswith("OK")


def test_committed_act_has_action_name_and_round_trips(tmp_path):
    store = _store(tmp_path)
    act = _act()
    res = store.commit_act(act)
    entries = store._storage.read(res.shard, limit=100)
    assert entries and all(e.metadata.get("action_name") == "prl.consultation" for e in entries)
    back = from_entry(entries[0])
    assert isinstance(back, ConsultationNode)
    assert back.answer == act.answer and back.mode == "observation"
    assert back.mef.producer == "claude via adapter v1"


# --- RR-only read path by action_name --------------------------------------

def test_consultation_readable_via_rr(tmp_path):
    store = _store(tmp_path)
    res = store.commit_act(_act())

    builder = RRIndexBuilder(storage=store._storage, index_dir=str(tmp_path / "rr"))
    builder.build()
    nav = RRNavigator(builder, store._storage)

    records = nav.navigate_action("prl.consultation")
    entries = nav.resolve_entries(records)
    acts = [from_entry(e) for e in entries]
    assert any(getattr(a, "consultation_id", None) == res.act_id for a in acts)


# --- R-consult v2: read/display via ConsultationQuery + CLI (kernel) --------

def test_consultation_query_reads_via_rr(tmp_path):
    from prl.query.consultation_read import ConsultationQuery

    store = _store(tmp_path)
    a = ConsultationAdapter()
    store.commit_act(a.to_act(subject_id="ko-A", answer="obs",
                              producer="claude via adapter v1", agent_id="agent.test",
                              confidence=0.6))
    store.commit_act(a.to_act(subject_id="ko-B", answer="prop",
                              producer="gpt via adapter v1", agent_id="agent.test",
                              confidence=0.8, propose=True))

    views = ConsultationQuery(store._storage, tmp_path / "rr").list()
    by_subj = {v.subject_id: v for v in views}
    assert {"ko-A", "ko-B"} <= set(by_subj)
    assert by_subj["ko-A"].mode == "observation" and by_subj["ko-B"].mode == "proposal"
    assert by_subj["ko-A"].receipt and by_subj["ko-B"].receipt  # DSM receipt = entry hash

    only_b = ConsultationQuery(store._storage, tmp_path / "rr2").list(subject_id="ko-B")
    assert [v.subject_id for v in only_b] == ["ko-B"]


def test_same_agent_id_two_carriers(tmp_path):
    """ADR-0009: the logical contributor (agent_id) is stable across executions; the
    carrier-of-record is not. Same agent.architect, two different carriers (models) →
    both views show the SAME agent_id but DIFFERENT carrier."""
    from prl.query.consultation_read import ConsultationQuery

    store = _store(tmp_path)
    a = ConsultationAdapter()
    store.commit_act(a.to_act(
        subject_id="ko-C", answer="via gpt-4o", producer="openai:gpt-4o (consult-adapter v1)",
        agent_id="agent.architect",
        carrier=Carrier(provider="openai", model="gpt-4o"), confidence=0.7))
    store.commit_act(a.to_act(
        subject_id="ko-C", answer="via gpt-5", producer="openai:gpt-5 (consult-adapter v1)",
        agent_id="agent.architect",
        carrier=Carrier(provider="openai", model="gpt-5"), confidence=0.7))

    views = ConsultationQuery(store._storage, tmp_path / "rr").list(subject_id="ko-C")
    assert len(views) == 2
    assert {v.agent_id for v in views} == {"agent.architect"}   # same logical contributor
    assert {v.carrier for v in views} == {"openai:gpt-4o", "openai:gpt-5"}  # different carriers


def test_cli_consultations_e2e(tmp_path, capsys):
    from prl.config import PRLConfig
    from prl.query import cli
    from prl.store import open_store

    config = PRLConfig(declared_projects=[tmp_path], storage_dir=tmp_path / "dsm")
    open_store(config).commit_act(
        ConsultationAdapter().to_act(subject_id="ko-Z", answer="hi",
                                     producer="claude via adapter v1", agent_id="agent.test",
                                     confidence=0.7)
    )
    rc = cli.main(["consultations", "--storage-dir", str(tmp_path / "dsm"),
                   "--rr-index-dir", str(tmp_path / "rr")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OBSERVATION on ko-Z" in out and "DSM receipt:" in out


# --- R-consult v3: real-agent consult via CLI (fake client, kernel) --------

class _FakeAgentClient:
    provider = "openai"

    def complete(self, prompt, *, model):
        return "use prev_hash"


def test_cli_consult_writes_certified_act_then_readable(tmp_path, capsys, monkeypatch):
    """The v3 chain with a fake client (no network): consult → certified act →
    readable/displayable. Proves real-agent → certified Knowledge Act end-to-end."""
    from prl.query import cli

    monkeypatch.setattr(cli, "_make_agent_client", lambda provider: _FakeAgentClient())
    storage = str(tmp_path / "dsm")

    rc = cli.main(["consult", "--provider", "openai", "--model", "gpt-5",
                   "--agent-id", "agent.test",
                   "--subject", "KO-123", "Should Storage.append expose prev_hash?",
                   "--storage-dir", storage])
    out = capsys.readouterr().out
    assert rc == 0
    assert "agent_id: agent.test" in out and "carrier: openai:gpt-5" in out
    assert "act: observation" in out and "DSM receipt:" in out

    rc2 = cli.main(["consultations", "--storage-dir", storage, "--subject", "KO-123",
                    "--rr-index-dir", str(tmp_path / "rr")])
    out2 = capsys.readouterr().out
    assert rc2 == 0
    assert "OBSERVATION on KO-123" in out2
    assert "openai:gpt-5 (consult-adapter v1)" in out2


# --- Resolution / Standing v1: proposal → human resolve → derived standing (kernel) --

def test_resolve_then_standing_derived(tmp_path):
    """Step 5 of the MVP scenario: a Proposal is human-ratified → certified Resolution
    act → the claim's standing is DERIVED as 'accepted' via RR (never stored)."""
    from prl.query import cli
    from prl.query.standing_read import StandingQuery

    store = _store(tmp_path)
    # a Proposal carries the claim the human will resolve
    proposal = ConsultationAdapter().to_act(
        subject_id="KO-9", answer="X", producer="claude via adapter v1", agent_id="agent.test",
        confidence=0.7, propose=True)
    store.commit_act(proposal)
    claim = proposal.mef.claim_id

    # before resolution: derived standing is 'proposed'
    assert StandingQuery(store._storage, tmp_path / "rr0").standing_of(claim).standing == "proposed"

    # human ratifies via CLI (write a Resolution act)
    rc = cli.main(["resolve", "--claim", claim, "--decision", "accepted",
                   "--agent-id", "mohamed.azizi", "--storage-dir", str(tmp_path)])
    assert rc == 0

    # standing is now DERIVED as 'accepted' (computed from acts, no stored field)
    view = StandingQuery(store._storage, tmp_path / "rr1").standing_of(claim)
    assert view.standing == "accepted"
    assert view.last_receipt  # the Resolution's DSM receipt


def test_cli_standing_e2e(tmp_path, capsys):
    from prl.query import cli

    store = _store(tmp_path)
    proposal = ConsultationAdapter().to_act(
        subject_id="KO-9", answer="X", producer="claude via adapter v1", agent_id="agent.test",
        confidence=0.7, propose=True)
    store.commit_act(proposal)
    claim = proposal.mef.claim_id

    cli.main(["resolve", "--claim", claim, "--decision", "accepted",
              "--agent-id", "mohamed.azizi", "--storage-dir", str(tmp_path)])
    capsys.readouterr()
    rc = cli.main(["standing", "--claim", claim, "--storage-dir", str(tmp_path),
                   "--rr-index-dir", str(tmp_path / "rr")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ACCEPTED" in out


def test_standing_latest_resolution_wins_through_kernel(tmp_path):
    """Multiple resolutions on one claim through the real kernel: standing is the
    LATEST decision (append order), not whatever order RR's resolve_entries returns.
    Regression guard — resolve_entries regroups by shard and does not preserve the
    navigate_action ordering, so derivation must replay by record order."""
    from prl.query.standing_read import StandingQuery

    store = _store(tmp_path)
    proposal = ConsultationAdapter().to_act(
        subject_id="KO-9", answer="X", producer="claude via adapter v1", agent_id="agent.test",
        confidence=0.7, propose=True)
    store.commit_act(proposal)
    claim = proposal.mef.claim_id

    store.commit_act(make_resolution(
        target_claim_id=claim, decision="accepted", agent_id="mohamed.azizi", claim_id=claim))
    store.commit_act(make_resolution(
        target_claim_id=claim, decision="superseded", agent_id="mohamed.azizi", claim_id=claim))

    view = StandingQuery(store._storage, tmp_path / "rr").standing_of(claim)
    assert view.standing == "superseded"                     # latest act wins
    assert view.decisions == ("accepted", "superseded")      # in append order


# --- R-explain v1: reconstruct "why this decision?" from certified acts (kernel) ----

def test_explain_reconstructs_chain_through_kernel(tmp_path):
    """Step 6: given a claim, reconstruct Proposal → Resolution → derived standing from
    certified acts only (no narration). Every facet carries its DSM receipt."""
    from prl.query.explain_read import ExplainQuery

    store = _store(tmp_path)
    proposal = ConsultationAdapter().to_act(
        subject_id="KO-7", answer="derived only", producer="openai:gpt-4o (consult-adapter v1)",
        agent_id="agent.test", confidence=0.7, propose=True)
    p_res = store.commit_act(proposal)
    claim = proposal.mef.claim_id
    r_res = store.commit_act(make_resolution(
        target_claim_id=claim, decision="accepted", agent_id="mohamed.azizi"))

    e = ExplainQuery(store._storage, tmp_path / "rr").explain(claim)
    assert e.proposal is not None and e.proposal.receipt == p_res.tip_hash
    assert e.proposal.producer == "openai:gpt-4o (consult-adapter v1)"
    assert len(e.resolutions) == 1
    assert e.resolutions[0].decision == "accepted"
    assert e.resolutions[0].agent_id == "mohamed.azizi"
    assert e.resolutions[0].carrier == "human"
    assert e.resolutions[0].receipt == r_res.tip_hash
    assert e.standing == "accepted"


def test_cli_explain_e2e(tmp_path, capsys):
    from prl.query import cli

    store = _store(tmp_path)
    proposal = ConsultationAdapter().to_act(
        subject_id="KO-7", answer="X", producer="openai:gpt-4o (consult-adapter v1)",
        agent_id="agent.test", confidence=0.7, propose=True)
    store.commit_act(proposal)
    claim = proposal.mef.claim_id
    cli.main(["resolve", "--claim", claim, "--decision", "accepted",
              "--agent-id", "mohamed.azizi", "--storage-dir", str(tmp_path)])
    capsys.readouterr()

    rc = cli.main(["explain", "--claim", claim, "--storage-dir", str(tmp_path),
                   "--rr-index-dir", str(tmp_path / "rr")])
    out = capsys.readouterr().out
    assert rc == 0
    assert f"why {claim} is ACCEPTED" in out
    assert "agent=mohamed.azizi" in out
    assert "carrier=human" in out
    assert "standing   governed=ACCEPTED  raw=ACCEPTED (latest-wins) (derived, ADR-0011)" in out
    assert out.count("receipt v1:") == 2


# --- Identity across projections v1: RR == SQLite (kernel) --------------------------

def test_identity_rr_equals_sqlite_projection(tmp_path):
    """Second epoch #3: the same acts, the same claim_id, two registry projections (RR and
    SQLite) → identical standing AND explanation, with receipts carried verbatim. The same
    StandingQuery/ExplainQuery code runs on both projections."""
    from prl.projections import SqliteProjection, build_sqlite_projection
    from prl.query.explain_read import ExplainQuery
    from prl.query.standing_read import StandingQuery

    store = _store(tmp_path)
    proposal = ConsultationAdapter().to_act(
        subject_id="KO-7", answer="derived only", producer="openai:gpt-4o (consult-adapter v1)",
        agent_id="agent.test", confidence=0.7, propose=True)
    p_res = store.commit_act(proposal)
    claim = proposal.mef.claim_id
    r_res = store.commit_act(make_resolution(
        target_claim_id=claim, decision="accepted", agent_id="mohamed.azizi"))

    db = str(tmp_path / "proj.sqlite")
    n = build_sqlite_projection(store._storage, tmp_path / "rr", db)
    assert n == 2
    sql = SqliteProjection(db)

    rr_explain = ExplainQuery(store._storage, tmp_path / "rr2").explain(claim)
    sq_explain = ExplainQuery(None, None, _navigator=sql).explain(claim)
    assert rr_explain == sq_explain                       # identical Explanation (by value)
    assert StandingQuery(None, None, _navigator=sql).standing_of(claim) == \
           StandingQuery(store._storage, tmp_path / "rr3").standing_of(claim)

    # identity + receipts carried verbatim across the projection
    assert sq_explain.proposal.receipt == p_res.tip_hash
    assert [r.receipt for r in sq_explain.resolutions] == [r_res.tip_hash]
    assert sq_explain.standing == "accepted"


def test_identity_latest_wins_survives_projection(tmp_path):
    """The ordering invariant (latest-wins) must survive materialization into SQLite."""
    from prl.projections import SqliteProjection, build_sqlite_projection
    from prl.query.standing_read import StandingQuery

    store = _store(tmp_path)
    proposal = ConsultationAdapter().to_act(
        subject_id="KO-7", answer="X", producer="openai:gpt-4o (consult-adapter v1)",
        agent_id="agent.test", confidence=0.7, propose=True)
    store.commit_act(proposal)
    claim = proposal.mef.claim_id
    store.commit_act(make_resolution(target_claim_id=claim, decision="accepted", agent_id="mohamed.azizi"))
    store.commit_act(make_resolution(target_claim_id=claim, decision="superseded", agent_id="alex.doe"))

    db = str(tmp_path / "proj.sqlite")
    build_sqlite_projection(store._storage, tmp_path / "rr", db)
    sq = StandingQuery(None, None, _navigator=SqliteProjection(db)).standing_of(claim)
    rr = StandingQuery(store._storage, tmp_path / "rr2").standing_of(claim)
    assert sq == rr
    assert sq.standing == "superseded" and sq.decisions == ("accepted", "superseded")


def test_cli_project_sqlite_then_explain_e2e(tmp_path, capsys):
    from prl.query import cli

    store = _store(tmp_path)
    proposal = ConsultationAdapter().to_act(
        subject_id="KO-7", answer="X", producer="openai:gpt-4o (consult-adapter v1)",
        agent_id="agent.test", confidence=0.7, propose=True)
    store.commit_act(proposal)
    claim = proposal.mef.claim_id
    cli.main(["resolve", "--claim", claim, "--decision", "accepted",
              "--agent-id", "mohamed.azizi", "--storage-dir", str(tmp_path)])
    capsys.readouterr()

    db = str(tmp_path / "proj.sqlite")
    rc = cli.main(["project-sqlite", "--storage-dir", str(tmp_path),
                   "--rr-index-dir", str(tmp_path / "rr"), "--db", db])
    assert rc == 0 and "sqlite projection built" in capsys.readouterr().out

    rc = cli.main(["explain", "--claim", claim, "--projection", "sqlite", "--db", db])
    out = capsys.readouterr().out
    assert rc == 0
    assert f"why {claim} is ACCEPTED" in out
    assert "agent=mohamed.azizi" in out
    assert "carrier=human" in out
    assert "standing   governed=ACCEPTED  raw=ACCEPTED (latest-wins) (derived, ADR-0011)" in out


# --- Derived standing at scale v1: StandingIndex bounded cost (kernel measurement) ---

def test_standing_index_bounded_cost_kernel(tmp_path):
    """#1 runtime proof on the real kernel (no credentials): R resolutions across M claims.
    StandingIndex builds in ONE bucket pass and answers every query with 0 further scans;
    StandingQuery rescans the bucket once per query (M scans). Both yield the IDENTICAL
    standing for every claim — the optimization memoizes the act *grouping*, never the
    standing (derive_standing stays the single source). Falsifiable, in-suite, measured."""
    from prl.query.standing_read import StandingIndex, StandingQuery, derive_standing

    store = _store(tmp_path)
    M, R = 6, 3  # M claims × R resolutions each → R*M certified resolution acts
    claims = [f"claim-scale-{i}" for i in range(M)]
    decisions = ["accepted", "rejected", "superseded"][:R]  # latest in append order = superseded
    for c in claims:
        for d in decisions:
            store.commit_act(make_resolution(
                target_claim_id=c, decision=d, agent_id="mohamed.azizi"))

    # one real RR navigator, wrapped to COUNT navigate_action("prl.resolution") scans
    builder = RRIndexBuilder(storage=store._storage, index_dir=str(tmp_path / "rr"))
    builder.build()
    real = RRNavigator(builder, store._storage)

    class _Counting:
        def __init__(self, nav):
            self._nav = nav
            self.scans = 0

        def navigate_action(self, action, limit=None):
            if action == "prl.resolution":
                self.scans += 1
            return self._nav.navigate_action(action, limit)

        def resolve_entries(self, records, limit=None):
            return self._nav.resolve_entries(records, limit)

    nav_idx = _Counting(real)
    index = StandingIndex(None, None, _navigator=nav_idx)   # ONE scan to build the grouping
    nav_q = _Counting(real)
    query = StandingQuery(None, None, _navigator=nav_q)     # no scan until queried

    # identical standing for every claim (latest-wins), and StandingIndex never stores it
    for c in claims:
        assert index.standing_of(c) == query.standing_of(c)
        assert index.standing_of(c).standing == "superseded"
        assert index.standing_of(c) == derive_standing(c, index.resolutions_of(c))

    # measured cost: index = 1 bucket pass total; query = one rescan per claim (M scans)
    assert nav_idx.scans == 1            # built once, 0 scans per query
    assert nav_q.scans == M              # StandingQuery rescans the bucket every query
    assert nav_q.scans > nav_idx.scans   # the bound holds — O(N)-once vs O(N)-per-query

    # drop the index ⇒ standing still correct from the acts (projection, never a source)
    rebuilt = StandingIndex(None, None, _navigator=_Counting(real))
    for c in claims:
        assert rebuilt.standing_of(c) == query.standing_of(c)
