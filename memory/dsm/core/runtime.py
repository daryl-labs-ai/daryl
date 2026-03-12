# dsm_v2/core/runtime.py
from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

RUNTIME_DIR = Path("data/runtime")
LAST_SHUTDOWN = RUNTIME_DIR / "last_shutdown.json"


@dataclass
class ShutdownState:
    reason: str
    signal: Optional[int]
    pid: int
    ts: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_last_shutdown(
    reason: str,
    sig: Optional[int] = None,
    extra: Optional[dict] = None,
) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": utc_now_iso(),
        "pid": os.getpid(),
        "reason": reason,
        "signal": sig,
    }
    if extra:
        payload["extra"] = extra

    tmp = LAST_SHUTDOWN.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LAST_SHUTDOWN)


def install_sigterm_handlers(
    on_shutdown: Callable[[str, Optional[int]], None],
    *,
    allow_double_signal_fast_exit: bool = True,
) -> None:
    """
    Installe SIGTERM/SIGINT pour shutdown propre.

    - 1er signal => appel on_shutdown() et on laisse le loop sortir
    - 2ème signal => exit immédiat (optionnel)
    """
    state = {"first": True}

    def _handler(signum, frame):
        reason = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        if state["first"]:
            state["first"] = False
            try:
                on_shutdown(reason, signum)
            except Exception:
                # éviter de crasher dans le handler
                pass
        else:
            if allow_double_signal_fast_exit:
                os._exit(128 + signum)

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
