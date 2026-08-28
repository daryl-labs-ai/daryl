"""Deterministic, provider-independent token estimation.

HexaShard measures context sizes constantly (budget enforcement, epoch
rotation, instrumentation).  Depending on a provider tokenizer would make the
core non-deterministic and provider-coupled, so the default counter is a plain
character-ratio *estimator*.  It is not a tokenizer and does not claim to match
any provider's count; it exists so that sizes are comparable and reproducible.

A caller who needs provider-exact numbers injects their own counter --
any ``Callable[[str], int]`` satisfies :class:`TokenCounter`.
"""

from __future__ import annotations

import json
import math
from typing import Any, Protocol

#: Characters per token used by the default estimator.
CHARS_PER_TOKEN = 4.0


class TokenCounter(Protocol):
    def __call__(self, text: str) -> int:  # pragma: no cover - protocol
        ...


def estimate_tokens(text: str) -> int:
    """Default counter: ``ceil(len(text) / CHARS_PER_TOKEN)``."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def json_tokens(obj: Any, counter: TokenCounter = estimate_tokens) -> int:
    """Token cost of a JSON-serialisable object in its serialised form.

    Serialisation is canonical (sorted keys, no spaces) so the number depends
    only on content, never on dict ordering.
    """
    return counter(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
