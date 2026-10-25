"""Durable quota pause mechanics for project-owned dispatch adapters.

This module stores per-provider, per-window pause observations. It deliberately
does not choose providers, define provider windows, parse provider output, or
decide whether an execution is eligible.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import time
from typing import Any

from .runtime import atomic, read


class QuotaLedger:
    """Persist block/reset observations using the V2.1 Mars ledger shape.

    ``windows_by_provider`` is supplied by the consumer adapter. Each provider
    is initialized with those windows plus an ``unknown`` window. A known reset
    expires automatically; an unknown reset remains blocked until the consumer
    records a newer observation or otherwise changes the ledger.
    """

    def __init__(self, path: str | Path, host: str,
                 windows_by_provider: Mapping[str, Sequence[str]], *,
                 clock: Callable[[], float] = time.time) -> None:
        self.path = Path(path)
        self.host = host
        self.clock = clock
        if not self.path.exists():
            atomic(self.path, {
                "host": host,
                "providers": {
                    provider: {
                        window: {"blocked": False, "reset_at": None}
                        for window in [*windows, "unknown"]
                    }
                    for provider, windows in windows_by_provider.items()
                },
            })

    def block(self, result: Mapping[str, Any]) -> None:
        """Persist a provider/window block observation atomically."""
        data = read(self.path)
        windows = data["providers"].setdefault(result["provider"], {})
        windows[result.get("window", "unknown")] = {
            **result,
            "blocked": True,
            "observed_at": self.clock(),
        }
        atomic(self.path, data)

    def blocked(self, provider: str) -> list[dict[str, Any]]:
        """Return active block observations for one provider at the injected time."""
        windows = read(self.path)["providers"].get(provider, {})
        now = self.clock()
        return [
            {**value, "window": key}
            for key, value in windows.items()
            if value.get("blocked")
            and (value.get("reset_at") is None or value["reset_at"] > now)
        ]
