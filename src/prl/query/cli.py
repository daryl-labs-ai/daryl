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

from ..collectors import ChatGPTCollector, FullTextSource, bind_sessions
from ..config import PRLConfig
from ..exceptions import PRLError
from ..index import build_map, make_project_node
from ..store import open_store, prl_shard_name
from .chunk_index import ChunkIndex
from .fusion_index import FusionIndex
from .recall import RecallEngine
from .semantic import LocalEmbedder, SemanticIndex


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

    return parser


def _make_embedder(model_name: str):
    """Factory for the recall embedder (overridable in tests). Defaults to the
    local sentence-transformers backend (optional ``[semantic]`` extra)."""
    return LocalEmbedder(model_name)


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
    return 1  # pragma: no cover (argparse 'required' guards this)
