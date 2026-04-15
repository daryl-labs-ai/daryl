"""Shared application state."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..adapters.daryl_adapter import CausalAdapter, ExchangeAdapter, SigningAdapter
from ..config import Config
from ..dsm.writer import DSMWriter
from ..index.db import IndexDB
from ..models.task import Task
from ..registry.agent_registry import AgentRegistry
from ..scheduler.task_scheduler import TaskScheduler


@dataclass
class AppState:
    config: Config
    index_db: IndexDB
    registry: AgentRegistry
    signing_adapter: SigningAdapter
    causal_adapter: CausalAdapter
    exchange_adapter: ExchangeAdapter
    dsm_writer: DSMWriter
    scheduler: TaskScheduler
    tasks: dict[str, Task] = field(default_factory=dict)
    missions: dict[str, dict] = field(default_factory=dict)
