"""PRL command-line interface (P4) — closes Phase 1.

    python -m prl index [--project PATH] [--config PATH] [--storage-dir PATH]
    python -m prl status [--config PATH]

``index`` scans the declared project folders, builds each project map (files +
git commits + edges), and commits it to DSM via the P3 store. ``status`` is a
config-level summary (declared projects + their shards) — it does **not** read
committed DSM data: per ADR-0001 reads go through RR, which lands in P5.

The CLI imports ``open_store`` from ``prl.store`` (the registered writer) rather
than ``Storage`` directly, so it needs no ``LEGITIMATE_WRITERS`` entry of its own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..collectors import (
    ChatGPTCollector,
    ConsultationAdapter,
    FullTextSource,
    OpenAIClient,
    bind_sessions,
    make_resolution,
)
from ..config import PRLConfig
from ..exceptions import PRLError
from ..index import build_map, make_project_node
from ..store import open_storage, open_store, prl_shard_name
from .chunk_index import ChunkIndex
from .consultation_read import ConsultationQuery, render_consultations
from .fusion_index import FusionIndex
from .explain_read import ExplainQuery, render_explanation
from .recall import RecallEngine
from .semantic import LocalEmbedder, SemanticIndex
from .standing_read import StandingQuery, render_standing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prl", description="Project Recall Layer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="scan declared projects and commit their map to DSM")
    p_index.add_argument("--project", help="index a single folder (ad-hoc, no config file needed)")
    p_index.add_argument("--config", help="path to the PRL config JSON")
    p_index.add_argument("--storage-dir", dest="storage_dir", help="override the DSM storage dir")

    p_status = sub.add_parser("status", help="show declared projects and their shards")
    p_status.add_argument("--config", help="path to the PRL config JSON")

    p_ask = sub.add_parser("ask", help="natural-language recall over a project + chat export")
    p_ask.add_argument("question", help="the natural-language question")
    p_ask.add_argument("--project", required=True, help="project folder to map")
    p_ask.add_argument("--export", required=True, help="ChatGPT export JSON to collect sessions from")
    p_ask.add_argument("-k", type=int, default=5, help="number of hits to return")
    p_ask.add_argument("--candidate-k", dest="candidate_k", type=int, default=None,
                       help="retrieval depth before the binder (default from config, 50); "
                            "decoupled from -k so the binder can rescue deeper candidates")
    p_ask.add_argument("--min-confidence", dest="min_confidence", type=float, default=0.40,
                       help="binder edge confidence threshold")
    p_ask.add_argument("--index-dir", dest="index_dir",
                       help="persist/load the retrieval indices here (latency cache); "
                            "delete the directory to force a rebuild")

    p_consult = sub.add_parser("consultations",
                               help="list recorded agent consultation acts (RR read, ADR-0008)")
    p_consult.add_argument("--config", help="path to the PRL config JSON")
    p_consult.add_argument("--storage-dir", dest="storage_dir", help="override the DSM storage dir")
    p_consult.add_argument("--subject", help="filter to one Knowledge Object / subject id")
    p_consult.add_argument("--rr-index-dir", dest="rr_index_dir",
                           help="directory for RR's derived index (default: <storage-dir>/_rr_index)")

    p_do = sub.add_parser("consult",
                          help="consult a real agent → DSM-certified Knowledge Act (ADR-0008, v3)")
    p_do.add_argument("prompt", help="the prompt sent to the real agent")
    p_do.add_argument("--provider", default="openai", help="agent provider (default: openai)")
    p_do.add_argument("--model", required=True, help="model name (e.g. gpt-5)")
    p_do.add_argument("--subject", required=True, help="the Knowledge Object / subject id")
    p_do.add_argument("--config", help="path to the PRL config JSON")
    p_do.add_argument("--storage-dir", dest="storage_dir", help="override the DSM storage dir")
    p_do.add_argument("--confidence", type=float, default=1.0,
                      help="confidence in the OBSERVATION (the agent answered), not its truth")
    p_do.add_argument("--propose", action="store_true",
                      help="record as Observation+Proposal instead of Observation (explicit only)")

    p_res = sub.add_parser("resolve",
                           help="human-ratify a claim → certified Resolution act (ADR-0008, Resolution v1)")
    p_res.add_argument("--claim", required=True, dest="claim", help="the target claim_id to resolve")
    p_res.add_argument("--decision", required=True,
                       choices=["accepted", "rejected", "superseded", "withdrawn"],
                       help="the governance decision (Accepted ≠ True)")
    p_res.add_argument("--producer", default="human:cli",
                       help="the human/witnessed ratifier (e.g. human:<id>); agents never ratify")
    p_res.add_argument("--config", help="path to the PRL config JSON")
    p_res.add_argument("--storage-dir", dest="storage_dir", help="override the DSM storage dir")

    p_st = sub.add_parser("standing",
                          help="show a claim's DERIVED standing (read-only, RR; never stored)")
    p_st.add_argument("--claim", required=True, dest="claim", help="the claim_id to derive standing for")
    p_st.add_argument("--config", help="path to the PRL config JSON")
    p_st.add_argument("--storage-dir", dest="storage_dir", help="override the DSM storage dir")
    p_st.add_argument("--rr-index-dir", dest="rr_index_dir",
                      help="directory for RR's derived index (default: <storage-dir>/_rr_index)")

    p_ex = sub.add_parser("explain",
                          help="reconstruct WHY a claim holds its standing, from certified acts (read-only)")
    p_ex.add_argument("--claim", required=True, dest="claim", help="the claim_id to explain")
    p_ex.add_argument("--config", help="path to the PRL config JSON")
    p_ex.add_argument("--storage-dir", dest="storage_dir", help="override the DSM storage dir")
    p_ex.add_argument("--rr-index-dir", dest="rr_index_dir",
                      help="directory for RR's derived index (default: <storage-dir>/_rr_index)")

    return parser


def _make_embedder(model_name: str):
    """Factory for the recall embedder (overridable in tests). Defaults to the
    local sentence-transformers backend (optional ``[semantic]`` extra)."""
    return LocalEmbedder(model_name)


def _make_agent_client(provider: str):
    """Factory for the real-agent client (overridable in tests → fake, no network).
    v3 ships the OpenAI provider only; others are future implementations."""
    if provider == "openai":
        return OpenAIClient()
    raise PRLError(f"unknown agent provider: {provider!r} (v3 supports: openai)")


def _resolve_config(args: argparse.Namespace) -> PRLConfig:
    if getattr(args, "project", None):
        config = PRLConfig(declared_projects=[Path(args.project)])
    elif getattr(args, "config", None):
        config = PRLConfig.load(Path(args.config))
    else:
        config = PRLConfig.load()
    storage_dir = getattr(args, "storage_dir", None)
    if storage_dir:
        config = config.model_copy(update={"storage_dir": Path(storage_dir)})
    return config


def cmd_index(args: argparse.Namespace) -> int:
    try:
        config = _resolve_config(args)
    except PRLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    store = open_store(config)
    for root in config.declared_projects:
        project = make_project_node(root)
        pmap = build_map(project, config)
        res = store.commit_map(pmap)
        print(
            f"✓ {project.name}: {len(pmap.files)} files, "
            f"{len(pmap.commits)} commits, {len(pmap.edges)} edges "
            f"→ {res.shard} (tip {res.tip_hash[:19]})"
        )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        config = (
            PRLConfig.load(Path(args.config)) if getattr(args, "config", None) else PRLConfig.load()
        )
    except PRLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"storage_dir: {config.storage_dir}")
    print(f"declared projects: {len(config.declared_projects)}")
    for root in config.declared_projects:
        project = make_project_node(root)
        print(f"  - {project.name}  [{prl_shard_name(project.project_id)}]  {root}")
    return 0


def cmd_consultations(args: argparse.Namespace) -> int:
    """List recorded consultation acts (R-consult v2, ADR-0008). Read-only: opens a
    Storage via prl/store and reads ``prl.consultation`` through RR. No writer, no LLM."""
    try:
        if getattr(args, "config", None):
            config = PRLConfig.load(Path(args.config))
        else:
            # read path: declared_projects is irrelevant here — placeholder to satisfy the model
            config = PRLConfig(declared_projects=[Path(".")])
        if getattr(args, "storage_dir", None):
            config = config.model_copy(update={"storage_dir": Path(args.storage_dir)})

        storage = open_storage(config)  # raw Storage from the registered store module (read)
        rr_dir = args.rr_index_dir or (Path(config.storage_dir) / "_rr_index")
        views = ConsultationQuery(storage, rr_dir).list(subject_id=getattr(args, "subject", None))
    except PRLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_consultations(views))
    return 0


def cmd_consult(args: argparse.Namespace) -> int:
    """R-consult v3: consult a real agent and commit its answer as a DSM-certified
    Knowledge Act. The model is unaware of PRL; the adapter maps native answer → act,
    prl/store certifies it. Default = Observation; --propose for Observation+Proposal."""
    try:
        if getattr(args, "config", None):
            config = PRLConfig.load(Path(args.config))
        else:
            config = PRLConfig(declared_projects=[Path(".")])  # write path: declared_projects unused
        if getattr(args, "storage_dir", None):
            config = config.model_copy(update={"storage_dir": Path(args.storage_dir)})

        client = _make_agent_client(args.provider)  # real model (test monkeypatches this)
        node = ConsultationAdapter().consult(
            client, subject_id=args.subject, prompt=args.prompt, model=args.model,
            confidence=args.confidence, propose=args.propose,
        )
        res = open_store(config).commit_act(node)
    except PRLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"✓ provider: {args.provider}")
    print(f"✓ model: {args.model}")
    print(f"✓ act: {node.mode}")
    print(f"✓ DSM receipt: {res.tip_hash}")
    return 0


def _read_config(args: argparse.Namespace) -> PRLConfig:
    """Resolve a config for a read/governance command. ``declared_projects`` is
    irrelevant to these commands; a placeholder satisfies the model when only a
    storage dir is given."""
    config = PRLConfig.load(Path(args.config)) if getattr(args, "config", None) \
        else PRLConfig(declared_projects=[Path(".")])
    if getattr(args, "storage_dir", None):
        config = config.model_copy(update={"storage_dir": Path(args.storage_dir)})
    return config


def cmd_resolve(args: argparse.Namespace) -> int:
    """Human-ratify a claim → certified Resolution act (Resolution v1). Write via
    prl/store; the agent path cannot reach this. An act, not a mutation — standing
    is derived later, not set here."""
    try:
        config = _read_config(args)
        node = make_resolution(
            target_claim_id=args.claim, decision=args.decision, producer=args.producer)
        res = open_store(config).commit_act(node)
    except PRLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"✓ resolved claim: {args.claim}")
    print(f"✓ decision: {args.decision}  (Accepted ≠ True)")
    print(f"✓ producer: {args.producer}")
    print(f"✓ DSM receipt: {res.tip_hash}")
    return 0


def cmd_standing(args: argparse.Namespace) -> int:
    """Show a claim's DERIVED standing (RR read-only; computed by replaying acts,
    never a stored field)."""
    try:
        config = _read_config(args)
        rr_dir = args.rr_index_dir or (Path(config.storage_dir) / "_rr_index")
        view = StandingQuery(open_storage(config), rr_dir).standing_of(args.claim)
    except PRLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_standing(view))
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    """Reconstruct WHY a claim holds its standing — Proposal → Resolution(s) → derived
    standing — from certified acts only (RR read-only; every line backed by a receipt)."""
    try:
        config = _read_config(args)
        rr_dir = args.rr_index_dir or (Path(config.storage_dir) / "_rr_index")
        explanation = ExplainQuery(open_storage(config), rr_dir).explain(args.claim)
    except PRLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_explanation(explanation))
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """Full in-memory recall: collect sessions → build map → bind → semantic
    search → structural enrichment → ranked, explainable hits. No LLM, no
    persisted state."""
    try:
        project = make_project_node(args.project)
        config = PRLConfig(declared_projects=[Path(args.project)])
        pmap = build_map(project, config)
        collector = ChatGPTCollector(args.export)
        sessions = collector.collect()
        edges = bind_sessions(sessions, pmap, min_confidence=args.min_confidence)

        embedder = _make_embedder(config.embedding_local_name)
        index_dir = getattr(args, "index_dir", None)

        # Retrieval Policy v2.0 (ADR-PRL-0006): conversation (preview) retriever +
        # passage (chunk) retriever, fused chunk-primary with a preview gate. The
        # heavy part is embedding the chunks; --index-dir caches those vectors.
        index: SemanticIndex | FusionIndex
        if index_dir and FusionIndex.is_persisted(index_dir):
            # Load cached vectors (no re-embedding). Invalidation is explicit:
            # delete the directory to rebuild after the export changes.
            index = FusionIndex.load(index_dir, embedder)
        else:
            preview = SemanticIndex(embedder)
            preview.build([(s.session_id, f"{s.title or ''} {s.text_preview}") for s in sessions])
            index = preview
            if isinstance(collector, FullTextSource):
                fulls = collector.full_texts()
                if fulls:
                    chunk = ChunkIndex(embedder, chunk_chars=config.retrieval_chunk_chars)
                    chunk.build([(s.session_id, f"{s.title or ''} {fulls.get(s.session_id, '')}")
                                 for s in sessions])
                    index = FusionIndex(
                        preview, chunk,
                        preview_gate=config.retrieval_preview_gate,
                        rrf_k=config.retrieval_rrf_k,
                    )
            if index_dir and isinstance(index, FusionIndex):
                index.save(index_dir)  # cache for next time (fusion path only)

        engine = RecallEngine(
            index,
            {s.session_id: s for s in sessions},
            edges,
            files={f.content_hash: f for f in pmap.files},
            commits={c.sha: c for c in pmap.commits},
        )
        candidate_k = (args.candidate_k if getattr(args, "candidate_k", None) is not None
                       else config.retrieval_candidate_k)
        hits = engine.ask(args.question, k=args.k, candidate_k=candidate_k)
    except PRLError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not hits:
        print("no confident match found")
        return 0
    for h in hits:
        print(f"▸ {h.session.title or h.session.session_id}  [score {h.score:.3f}]")
        print(f"    session: {h.session.session_id} ({h.session.tool})")
        if h.linked_files:
            print(f"    files: {', '.join(f.path for f in h.linked_files)}")
        if h.linked_commits:
            print(f"    commits: {', '.join(c.sha[:10] for c in h.linked_commits)}")
        print(f"    why: {'; '.join(h.why)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "index":
        return cmd_index(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "ask":
        return cmd_ask(args)
    if args.command == "consultations":
        return cmd_consultations(args)
    if args.command == "consult":
        return cmd_consult(args)
    if args.command == "resolve":
        return cmd_resolve(args)
    if args.command == "standing":
        return cmd_standing(args)
    if args.command == "explain":
        return cmd_explain(args)
    return 1  # pragma: no cover (argparse 'required' guards this)
