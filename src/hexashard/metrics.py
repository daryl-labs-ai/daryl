"""Provider-independent instrumentation.

Context size and compute are separate quantities and are recorded separately.
A small active state is not a claim about total tokens consumed; if a caller
never wires a model provider, the model counters stay at zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Metrics:
    # context
    active_state_tokens: int = 0
    active_state_peak_tokens: int = 0
    source_store_tokens: int = 0
    # retrieval
    retrieval_tokens: int = 0
    retrieval_count: int = 0
    # epochs
    epoch_rotations: int = 0
    handoff_tokens: list[int] = field(default_factory=list)
    # map
    pin_count: int = 0
    hot_hex_count: int = 0
    warm_hex_count: int = 0
    cold_hex_count: int = 0
    # model (zero unless a provider is actually used)
    model_calls: int = 0
    model_input_tokens: int = 0
    model_output_tokens: int = 0

    def observe_active_state(self, tokens: int) -> None:
        self.active_state_tokens = tokens
        self.active_state_peak_tokens = max(self.active_state_peak_tokens, tokens)

    def observe_retrieval(self, tokens: int) -> None:
        self.retrieval_count += 1
        self.retrieval_tokens += tokens

    def observe_model(self, input_tokens: int, output_tokens: int) -> None:
        self.model_calls += 1
        self.model_input_tokens += input_tokens
        self.model_output_tokens += output_tokens

    def to_dict(self) -> dict:
        return asdict(self)
