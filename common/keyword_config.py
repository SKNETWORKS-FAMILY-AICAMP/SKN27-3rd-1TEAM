from __future__ import annotations

import os
import re
from collections.abc import Iterable


def load_keyword_tuple(env_name: str, defaults: Iterable[str]) -> tuple[str, ...]:
    """Load comma/newline-separated keyword overrides while preserving defaults."""

    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return tuple(defaults)
    return tuple(
        keyword.strip()
        for keyword in re.split(r"[,\n]+", raw_value)
        if keyword.strip()
    )
