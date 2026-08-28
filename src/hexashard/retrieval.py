"""Retrieval: structured filters + lexical scoring + pin lookup.

Three deliberate properties:

*Authority first.*  The sort key is ``(authority_rank, lexical_score)``, so a
DRAFT, UNVERIFIED or SUPERSEDED fragment can never outrank a CURRENT one on
score alone.  By default only CURRENT sources are returned; history is
reachable only by asking for it explicitly.

*Deterministic.*  Same store + same query + same filters gives byte-identical
results.  Ties break on address.

*Extensible without being extended.*  Scoring sits behind a one-method
:class:`Scorer` protocol.  Swapping in an embedding scorer later touches this
file only; v0.1 ships BM25 and no vector infrastructure.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from .ids import fragment_address
from .models import Hex, Pin, Source, SourceStatus, authority_rank
from .store import HexMap, PinStore, RelationStore, SourceStore
from .tokens import TokenCounter, estimate_tokens

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_.\-]*")
DEFAULT_CHUNK_CHARS = 1200


def tokenize(text: str) -> list[str]:
    """Lowercase word/number/identifier pieces.  Keeps dotted addresses intact."""
    return _TOKEN_RE.findall(text.lower())


# --------------------------------------------------------------------------
# Fragments
# --------------------------------------------------------------------------


@dataclass
class Fragment:
    fragment_id: str
    source_id: str
    index: int
    text: str

    @property
    def tokens(self) -> list[str]:
        return tokenize(self.text)


def chunk(content: str, chunk_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    """Split on blank lines, then pack paragraphs up to ``chunk_chars``."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    out: list[str] = []
    buf = ""
    for p in paras:
        while len(p) > chunk_chars:
            if buf:
                out.append(buf)
                buf = ""
            out.append(p[:chunk_chars])
            p = p[chunk_chars:]
        if not buf:
            buf = p
        elif len(buf) + 2 + len(p) <= chunk_chars:
            buf = f"{buf}\n\n{p}"
        else:
            out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    return out


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


class Scorer(Protocol):
    def index(self, fragments: list[Fragment]) -> None: ...
    def score(self, query_tokens: list[str], fragment_ids: list[str]) -> dict[str, float]: ...


class BM25Scorer:
    """Okapi BM25.  Fixed parameters, no external dependency, deterministic."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self._tf: dict[str, Counter] = {}
        self._len: dict[str, int] = {}
        self._df: Counter = Counter()
        self._n = 0
        self._avg_len = 0.0

    def index(self, fragments: list[Fragment]) -> None:
        self._tf, self._len, self._df = {}, {}, Counter()
        for f in fragments:
            toks = f.tokens
            self._tf[f.fragment_id] = Counter(toks)
            self._len[f.fragment_id] = len(toks)
            for t in set(toks):
                self._df[t] += 1
        self._n = len(fragments)
        self._avg_len = (sum(self._len.values()) / self._n) if self._n else 0.0

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log(1.0 + (self._n - df + 0.5) / (df + 0.5))

    def score(self, query_tokens: list[str], fragment_ids: list[str]) -> dict[str, float]:
        out: dict[str, float] = {}
        for fid in fragment_ids:
            tf, dl = self._tf.get(fid), self._len.get(fid, 0)
            if not tf:
                continue
            s = 0.0
            for term in query_tokens:
                f = tf.get(term, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self._avg_len or 1.0))
                s += self._idf(term) * f * (self.k1 + 1) / denom
            if s > 0:
                out[fid] = round(s, 6)
        return out


# --------------------------------------------------------------------------
# Query surface
# --------------------------------------------------------------------------


@dataclass
class RetrievalFilters:
    """Structured narrowing applied before any scoring happens."""

    #: Which source authority states may be returned.  ``None`` means CURRENT only.
    statuses: tuple[SourceStatus, ...] | None = None
    include_superseded: bool = False
    source_ids: tuple[str, ...] | None = None
    source_types: tuple[str, ...] | None = None
    tags: tuple[str, ...] | None = None
    claim_key: str | None = None
    hex_ids: tuple[str, ...] | None = None
    hex_types: tuple[str, ...] | None = None
    epoch: int | None = None
    #: Restrict to hexes reachable from this hex in the relation graph.
    related_to: str | None = None
    relation_type: str | None = None

    def effective_statuses(self) -> set[SourceStatus]:
        if self.statuses is not None:
            # an empty tuple is an explicit "no status matches", not a default
            return {SourceStatus(s) for s in self.statuses}
        if self.include_superseded:
            return {SourceStatus.CURRENT, SourceStatus.SUPERSEDED}
        return {SourceStatus.CURRENT}

    def to_dict(self) -> dict:
        # `v not in (None, False)` would drop epoch=0, since 0 == False
        d = {k: v for k, v in self.__dict__.items()
             if v is not None and v is not False}
        if "statuses" in d:
            d["statuses"] = [SourceStatus(s).value for s in d["statuses"]]
        for k in ("source_ids", "source_types", "tags", "hex_ids", "hex_types"):
            if k in d:
                d[k] = list(d[k])
        d["effective_statuses"] = sorted(s.value for s in self.effective_statuses())
        return d


@dataclass
class ScoredFragment:
    fragment_id: str
    source_id: str
    source_title: str
    source_status: str
    authority: int
    score: float
    text: str
    tokens: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Ambiguity:
    """Two or more equally authoritative sources answer the same claim."""

    claim_key: str
    source_ids: list[str]
    reason: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class RetrievalResult:
    query: str
    fragments: list[ScoredFragment] = field(default_factory=list)
    hex_refs: list[str] = field(default_factory=list)
    pin_refs: list[str] = field(default_factory=list)
    ambiguities: list[Ambiguity] = field(default_factory=list)
    tokens: int = 0
    truncated: bool = False
    #: True when a single fragment alone exceeded the requested budget, so the
    #: result is over budget rather than merely cut short.
    over_budget: bool = False
    filters: dict = field(default_factory=dict)

    @property
    def source_ids(self) -> list[str]:
        out: list[str] = []
        for f in self.fragments:
            if f.source_id not in out:
                out.append(f.source_id)
        return out

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "fragments": [f.to_dict() for f in self.fragments],
            "hex_refs": list(self.hex_refs),
            "pin_refs": list(self.pin_refs),
            "ambiguities": [a.to_dict() for a in self.ambiguities],
            "tokens": self.tokens,
            "truncated": self.truncated,
            "over_budget": self.over_budget,
            "filters": self.filters,
        }


# --------------------------------------------------------------------------
# Retriever
# --------------------------------------------------------------------------


class Retriever:
    def __init__(
        self,
        sources: SourceStore,
        hexmap: HexMap,
        pins: PinStore,
        relations: RelationStore,
        *,
        scorer: Scorer | None = None,
        counter: TokenCounter = estimate_tokens,
        chunk_chars: int = DEFAULT_CHUNK_CHARS,
    ) -> None:
        self.sources = sources
        self.hexmap = hexmap
        self.pins = pins
        self.relations = relations
        self.scorer = scorer or BM25Scorer()
        self.counter = counter
        self.chunk_chars = chunk_chars
        self._fragments: dict[str, Fragment] = {}
        self._by_source: dict[str, list[str]] = {}
        self.reindex()

    # -- index -----------------------------------------------------------
    def reindex(self) -> int:
        """Rebuild the fragment index from the source store.

        Called explicitly after source mutations; there is no hidden cache
        invalidation to reason about.
        """
        self._fragments, self._by_source = {}, {}
        frags: list[Fragment] = []
        for src in self.sources.all():
            ids: list[str] = []
            for i, text in enumerate(chunk(src.content, self.chunk_chars)):
                fid = fragment_address(src.source_id, i)
                f = Fragment(fid, src.source_id, i, text)
                self._fragments[fid] = f
                frags.append(f)
                ids.append(fid)
            self._by_source[src.source_id] = ids
        self.scorer.index(frags)
        return len(frags)

    @property
    def fragment_count(self) -> int:
        return len(self._fragments)

    # -- candidate selection ---------------------------------------------
    def _candidate_sources(self, filters: RetrievalFilters) -> list[Source]:
        allowed = filters.effective_statuses()
        out = [s for s in self.sources.all() if s.status in allowed]
        if filters.source_ids is not None:
            want = set(filters.source_ids)
            out = [s for s in out if s.source_id in want]
        if filters.source_types is not None:
            want = set(filters.source_types)
            out = [s for s in out if s.source_type in want]
        if filters.tags is not None:
            want = set(filters.tags)
            out = [s for s in out if want & set(s.tags)]
        if filters.claim_key is not None:
            out = [s for s in out if s.claim_key == filters.claim_key]

        hex_scope = self._hex_scope(filters)
        if hex_scope is not None:
            allowed_sources: set[str] = set()
            for h in hex_scope:
                allowed_sources.update(h.source_refs)
            out = [s for s in out if s.source_id in allowed_sources]
        return out

    def _hex_scope(self, filters: RetrievalFilters) -> list[Hex] | None:
        if not any((filters.hex_ids, filters.hex_types, filters.epoch is not None,
                    filters.related_to)):
            return None
        hexes = self.hexmap.all()
        if filters.hex_ids is not None:
            want = set(filters.hex_ids)
            hexes = [h for h in hexes if h.hex_id in want]
        if filters.hex_types is not None:
            want = set(filters.hex_types)
            hexes = [h for h in hexes if h.type.value in want]
        if filters.epoch is not None:
            hexes = [h for h in hexes if h.epoch == filters.epoch]
        if filters.related_to is not None:
            reachable = set(self.relations.neighbours(filters.related_to,
                                                      type=filters.relation_type))
            reachable.add(filters.related_to)
            hexes = [h for h in hexes if h.hex_id in reachable]
        return hexes

    # -- query -----------------------------------------------------------
    def retrieve(
        self,
        query: str,
        filters: RetrievalFilters | None = None,
        budget: int = 1500,
        *,
        max_fragments: int = 8,
    ) -> RetrievalResult:
        """Retrieve grounding for ``query`` within a token ``budget``."""
        filters = filters or RetrievalFilters()
        qtokens = tokenize(query)
        candidates = self._candidate_sources(filters)
        by_id = {s.source_id: s for s in candidates}

        frag_ids: list[str] = []
        for s in candidates:
            frag_ids.extend(self._by_source.get(s.source_id, []))
        scores = self.scorer.score(qtokens, frag_ids)

        ranked = sorted(
            (fid for fid in frag_ids if fid in scores),
            key=lambda fid: (
                -authority_rank(by_id[self._fragments[fid].source_id].status),
                -scores[fid],
                self._fragments[fid].source_id,
                self._fragments[fid].index,
            ),
        )

        result = RetrievalResult(query=query, filters=filters.to_dict())
        used = 0
        for fid in ranked:
            if len(result.fragments) >= max_fragments:
                result.truncated = True
                break
            frag = self._fragments[fid]
            src = by_id[frag.source_id]
            cost = self.counter(frag.text)
            if used + cost > budget and result.fragments:
                result.truncated = True
                break
            result.fragments.append(
                ScoredFragment(
                    fragment_id=fid,
                    source_id=src.source_id,
                    source_title=src.title,
                    source_status=src.status.value,
                    authority=authority_rank(src.status),
                    score=scores[fid],
                    text=frag.text,
                    tokens=cost,
                )
            )
            used += cost
        result.tokens = used
        result.over_budget = used > budget

        result.ambiguities = self._ambiguities(ranked, by_id)
        result.hex_refs = self._hex_refs(result, qtokens)
        result.pin_refs = self._pin_refs(qtokens)
        return result

    def _ambiguities(self, ranked: list[str], by_id: dict[str, Source]) -> list[Ambiguity]:
        """Explicit authority conflicts on claims the query actually touched.

        Detection is structural, not a score heuristic.  A claim key enters
        scope as soon as *one* matching source declares it; every CURRENT
        source declaring that key is then counted, whether or not it scored.
        A rival that shares no vocabulary with the query is exactly the case a
        score-based check would miss, and is the reason this scan is separate
        from ranking.
        """
        in_scope = {
            by_id[self._fragments[fid].source_id].claim_key
            for fid in ranked
            if by_id[self._fragments[fid].source_id].claim_key
        }
        by_claim: dict[str, list[str]] = {}
        for src in self.sources.all():
            if src.claim_key in in_scope and src.status is SourceStatus.CURRENT:
                bucket = by_claim.setdefault(src.claim_key, [])
                if src.source_id not in bucket:
                    bucket.append(src.source_id)
        return [
            Ambiguity(
                claim_key=key,
                source_ids=sorted(ids),
                reason=(f"{len(ids)} CURRENT sources declare claim_key {key!r}; "
                        "authority cannot be resolved automatically"),
            )
            for key, ids in sorted(by_claim.items())
            if len(ids) > 1
        ]

    def _hex_refs(self, result: RetrievalResult, qtokens: list[str]) -> list[str]:
        refs: list[str] = []
        for sid in result.source_ids:
            h = self.hexmap.hex_for_source(sid)
            if h is not None and h.hex_id not in refs:
                refs.append(h.hex_id)
        qset = set(qtokens)
        for h in self.hexmap.all():
            if h.hex_id in refs:
                continue
            if qset & {t.lower() for t in h.tags}:
                refs.append(h.hex_id)
        return refs

    def _pin_refs(self, qtokens: list[str]) -> list[str]:
        qset = set(qtokens)
        scored: list[tuple[int, str]] = []
        for p in self.pins.live():
            overlap = len(qset & set(tokenize(f"{p.key} {p.value}")))
            if overlap:
                scored.append((-overlap, p.pin_id))
        return [pid for _, pid in sorted(scored)]

    # -- direct addressing ------------------------------------------------
    def by_address(self, address: str) -> Source | Hex | Pin | None:
        """Resolve any human-readable address without a search."""
        if "#" in address:
            frag = self._fragments.get(address)
            return self.sources.try_get(frag.source_id) if frag else None
        if ".S" in address:
            return self.sources.try_get(address)
        if ".H" in address:
            return self.hexmap.try_get(address)
        if ".K" in address:
            try:
                return self.pins.get(address)
            except KeyError:
                return None
        return None
