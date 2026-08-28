"""HexaShard command line. Boring on purpose: argparse, stdlib, no TUI.

    python -m hexashard_adapter create ./launch --name launch
    python -m hexashard_adapter source add ./launch --type spec --title "Budget" --text "..."
    python -m hexashard_adapter pin ./launch --key budget --value "2.4M EUR" --source Budget
    python -m hexashard_adapter chat ./launch --provider ollama

A project is not a chat session. The chat window can be empty, or a different
machine, or a different provider; the project is what persists. These commands
maintain the project. ``chat`` talks to a model about it.

Everything here is a thin pass-through to the existing Adapter and Core API.
The CLI holds no project model of its own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .adapter import HexaShardAdapter
from .config import AdapterConfig
from .errors import AdapterError, ProjectNotFound
from .provider import ollama_available


class CommandError(Exception):
    """A user-facing problem: bad arguments, ambiguous reference, missing project."""


# -- helpers --------------------------------------------------------------

def _open(root: str, *, mode: str = "NORMAL", provider: str = "mock") -> HexaShardAdapter:
    try:
        return HexaShardAdapter.open(
            Path(root), config=AdapterConfig(provider=provider, mode=mode)
        )
    except ProjectNotFound:
        raise CommandError(
            f"no project at {root}\n"
            f"  create one with:  python -m hexashard_adapter create {root} --name NAME"
        ) from None


def _resolve_source(project, ref: str):
    """Find a source by id or by title.

    Titles are what a person remembers, so they are accepted. Ambiguity is never
    guessed: two sources sharing a title is an error that lists both ids.
    """
    sources = project.sources.all()
    for s in sources:
        if s.source_id == ref:
            return s
    matches = [s for s in sources if s.title.strip().lower() == ref.strip().lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        known = ", ".join(f"{s.source_id} ({s.title})" for s in sources[:8]) or "none yet"
        raise CommandError(f"no source matches {ref!r}\n  known sources: {known}")
    listed = "\n".join(f"    {s.source_id}  {s.title}  [{s.status.value}]" for s in matches)
    raise CommandError(
        f"{ref!r} matches {len(matches)} sources — say which one by id:\n{listed}"
    )


def _content(args) -> str:
    if args.text and args.file:
        raise CommandError("give --text or --file, not both")
    if args.file:
        path = Path(args.file)
        if not path.is_file():
            raise CommandError(f"no such file: {args.file}")
        return path.read_text(encoding="utf-8")
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        body = sys.stdin.read()
        if body.strip():
            return body
    raise CommandError("no content: pass --text, --file, or pipe it on stdin")


# -- commands -------------------------------------------------------------

def cmd_create(args) -> int:
    root = Path(args.project)
    if (root / "project.json").exists():
        raise CommandError(f"a project already exists at {root}")
    adapter = HexaShardAdapter.create(
        root, name=args.name, mission=args.mission or "", config=AdapterConfig()
    )
    print(f"created project {args.name} at {root}")
    if args.mission:
        print(f"  mission: {args.mission}")
    adapter.close()
    return 0


def cmd_status(args) -> int:
    adapter = _open(args.project)
    st = adapter.project_status()
    print(f"project {st['name']}  epoch {st['epoch']}  turn {st['turn']}")
    if st["mission"]:
        print(f"  mission   {st['mission']}")
    if st["objective"]:
        print(f"  objective {st['objective']}")
    print(f"  sources   {st['source_count']}")
    print(f"  pins      {st['pin_count']}")
    print(f"  store     {st['project_store_tokens']} tokens")
    print(f"  active    {st['active_state_tokens']} tokens")
    open_qs = adapter.project.state.unresolved_questions()
    print(f"  open      {len(open_qs)} question(s)")
    for q in open_qs:
        print(f"      {q['id']}  {q['text']}")
    warnings = [r for r in adapter.project.check_pins() if r.status.value != "ACTIVE"]
    for w in warnings:
        print(f"  warning   pin {w.key} is {w.status.value}: {w.detail}")
    adapter.close()
    return 0


def cmd_source_add(args) -> int:
    adapter = _open(args.project)
    src = adapter.add_source(
        args.type, args.title, _content(args),
        tags=[t.strip() for t in (args.tags or "").split(",") if t.strip()],
        claim_key=args.claim_key, claim_value=args.claim_value,
    )
    adapter.project.save()
    print(f"added {src.source_id}  {src.title}  [{src.status.value}]")
    if args.claim_key:
        print(f"  declares claim {args.claim_key} = {args.claim_value}")
    adapter.close()
    return 0


def cmd_source_list(args) -> int:
    adapter = _open(args.project)
    for s in adapter.project.sources.all():
        print(f"{s.source_id}  [{s.status.value:10s}] {s.title}")
    adapter.close()
    return 0


def cmd_source_show(args) -> int:
    adapter = _open(args.project)
    s = _resolve_source(adapter.project, args.source)
    print(f"{s.source_id}  [{s.status.value}]  {s.title}")
    if s.superseded_by:
        print(f"  superseded by {s.superseded_by}")
    if s.claim_key:
        print(f"  claim {s.claim_key} = {s.claim_value}")
    print()
    print(s.content)
    adapter.close()
    return 0


def cmd_pin(args) -> int:
    adapter = _open(args.project)
    ref = None
    if args.source:
        ref = _resolve_source(adapter.project, args.source).source_id
    elif not args.ungrounded:
        raise CommandError(
            "a pin should point at the source that grounds it.\n"
            "  pass --source REF, or --ungrounded if you really mean to record a\n"
            "  value with nothing backing it (it will report as BROKEN)."
        )
    pin = adapter.pin(args.key, args.value, ref, critical=args.critical, note=args.note)
    adapter.project.save()
    grounding = f"grounded in {ref}" if ref else "UNGROUNDED"
    print(f"pinned {pin.pin_id}  {args.key} = {args.value}  ({grounding})"
          + ("  [CRITICAL]" if args.critical else ""))
    adapter.close()
    return 0


def cmd_supersede(args) -> int:
    adapter = _open(args.project)
    old = _resolve_source(adapter.project, args.old)
    new = _resolve_source(adapter.project, args.new)
    if old.source_id == new.source_id:
        raise CommandError("a source cannot supersede itself")
    out = adapter.supersede(old.source_id, new.source_id)
    adapter.project.save()
    print(f"{new.source_id} now supersedes {old.source_id}")
    print(f"  {old.source_id} is {old.status.value}, still retrievable as history")
    for rec in out.get("reconciliations") or []:
        print(f"  pin {rec.get('key')}: {rec.get('detail') or rec.get('status')}")
    for r in adapter.project.check_pins():
        if r.status.value != "ACTIVE":
            print(f"  warning   pin {r.key} is {r.status.value}: {r.detail}")
    for p in adapter.project.pins.all():
        if p.status.value != "ACTIVE":
            print(f"  warning   pin {p.key} still reads {p.value!r} and is marked "
                  f"{p.status.value} — confirm it against {p.source_ref}")
    adapter.close()
    return 0


def cmd_decision(args) -> int:
    adapter = _open(args.project)
    if adapter.config.mode == "READ_ONLY":
        raise CommandError("READ_ONLY: decisions are not allowed")
    ref = _resolve_source(adapter.project, args.source).source_id if args.source else None
    adapter.project.state.note_decision(hex_id="", title=args.text, source_ref=ref)
    adapter.project.save()
    print(f"recorded decision: {args.text}" + (f"  (source {ref})" if ref else ""))
    adapter.close()
    return 0


def cmd_question_add(args) -> int:
    adapter = _open(args.project)
    existing = {q["id"] for q in adapter.project.state.open_questions}
    qid = args.id
    if qid is None:
        n = 1
        while f"Q{n}" in existing:
            n += 1
        qid = f"Q{n}"
    elif qid in existing:
        raise CommandError(f"question {qid} already exists")
    adapter.project.state.add_open_question(qid, args.text)
    adapter.project.save()
    print(f"opened {qid}  {args.text}")
    adapter.close()
    return 0


def cmd_question_list(args) -> int:
    adapter = _open(args.project)
    qs = adapter.project.state.open_questions
    if not qs:
        print("no questions recorded")
    for q in qs:
        print(f"{q['id']}  [{'resolved' if q.get('resolved') else 'open'}]  {q['text']}")
    adapter.close()
    return 0


def cmd_question_resolve(args) -> int:
    adapter = _open(args.project)
    ids = {q["id"] for q in adapter.project.state.open_questions}
    if args.id not in ids:
        raise CommandError(f"no question {args.id}; known: {', '.join(sorted(ids)) or 'none'}")
    adapter.project.state.resolve_question(args.id)
    adapter.project.save()
    print(f"resolved {args.id}")
    adapter.close()
    return 0


def cmd_chat(args) -> int:
    root = Path(args.project)
    cfg = AdapterConfig(provider=args.provider, mode=args.mode)
    if args.provider == "ollama" and not ollama_available(cfg.endpoint):
        print("ollama unavailable; use --provider mock", file=sys.stderr)
        return 2
    try:
        adapter = HexaShardAdapter.open(root, config=cfg)
    except ProjectNotFound:
        print(f"no project at {root}", file=sys.stderr)
        return 2
    print(f"project {adapter.project.config.name}  epoch {adapter.project.state.epoch}  {args.provider}")
    if args.mode == "READ_ONLY":
        print("READ_ONLY: questions only; the project will not be changed")
    print("enter text; Ctrl-D to exit")
    try:
        while True:
            try:
                line = input("> ")
            except EOFError:
                print()
                break
            if not line.strip():
                continue
            try:
                result = adapter.chat(line.strip())
            except AdapterError as e:
                print(f"error: {e}")
                continue
            print(result.response_text)
            print(
                f"  [in={result.total_context_tokens} store={result.project_store_tokens} "
                f"epoch={result.epoch} trunc={result.truncated}]"
            )
    finally:
        adapter.close()
    return 0


# -- wiring ---------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hexashard_adapter",
        description="HexaShard v0.1 — a project that outlives the chat window.",
        epilog=(
            "the project is the thing that persists; chat is one way to ask about it.\n"
            "sources ground the project, pins point at sources, and neither a model\n"
            "answer nor a chat transcript ever becomes project truth on its own."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("project", help="path to the project directory")
        sp.set_defaults(func=fn)
        return sp

    add("create", cmd_create, "start a new project").add_argument("--name", required=True)
    sub.choices["create"].add_argument("--mission", default="", help="what the project is for")

    add("status", cmd_status, "what the project currently holds")

    src = sub.add_parser("source", help="primary material — what grounds the project")
    src_sub = src.add_subparsers(dest="sub", required=True, metavar="ACTION")
    sa = src_sub.add_parser("add", help="record a source")
    sa.add_argument("project")
    sa.add_argument("--type", required=True,
                    help="free text, e.g. spec, note, decision, legal")
    sa.add_argument("--title", required=True)
    sa.add_argument("--text", help="content inline")
    sa.add_argument("--file", help="content from a file")
    sa.add_argument("--tags", help="comma separated")
    sa.add_argument("--claim-key", dest="claim_key",
                    help="the fact this source is authoritative for, e.g. launch_date. "
                         "Declaring it lets a later supersession carry the value forward.")
    sa.add_argument("--claim-value", dest="claim_value", help="that fact's value")
    sa.set_defaults(func=cmd_source_add)
    sl = src_sub.add_parser("list", help="list sources")
    sl.add_argument("project")
    sl.set_defaults(func=cmd_source_list)
    ss = src_sub.add_parser("show", help="show one source")
    ss.add_argument("project")
    ss.add_argument("source", help="source id or title")
    ss.set_defaults(func=cmd_source_show)

    pin = add("pin", cmd_pin, "record an invariant that points at a source")
    pin.add_argument("--key", required=True)
    pin.add_argument("--value", required=True)
    pin.add_argument("--source", help="source id or title that grounds this value")
    pin.add_argument("--critical", action="store_true", help="always keep in the working set")
    pin.add_argument("--note", default=None)
    pin.add_argument("--ungrounded", action="store_true",
                     help="record a pin with no source behind it (reports BROKEN)")

    sup = add("supersede", cmd_supersede, "make one source replace another")
    sup.add_argument("--old", required=True, help="source id or title being replaced")
    sup.add_argument("--new", required=True, help="source id or title taking over")

    dec = add("decision", cmd_decision, "record a decision you have taken")
    dec.add_argument("text", help="the decision, in your words")
    dec.add_argument("--source", default=None, help="source id or title backing it")

    q = sub.add_parser("question", help="things not yet decided")
    q_sub = q.add_subparsers(dest="sub", required=True, metavar="ACTION")
    qa = q_sub.add_parser("add", help="open a question")
    qa.add_argument("project")
    qa.add_argument("--text", required=True)
    qa.add_argument("--id", default=None,
                    help="optional; allocated automatically if omitted")
    qa.set_defaults(func=cmd_question_add)
    ql = q_sub.add_parser("list", help="list questions")
    ql.add_argument("project")
    ql.set_defaults(func=cmd_question_list)
    qr = q_sub.add_parser("resolve", help="close a question")
    qr.add_argument("project")
    qr.add_argument("--id", required=True)
    qr.set_defaults(func=cmd_question_resolve)

    ch = add("chat", cmd_chat, "ask a model about the project")
    ch.add_argument("--provider", choices=("mock", "ollama"), default="mock")
    ch.add_argument("--mode", choices=("NORMAL", "READ_ONLY"), default="NORMAL",
                    help="READ_ONLY answers without changing the project")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CommandError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except AdapterError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except PermissionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
