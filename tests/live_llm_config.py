"""Shared environment handling for live Ollama evaluation providers."""

from __future__ import annotations

import os


def thinking_for_role(role: str) -> bool | None:
    """Resolve explicit role, live-evaluation, then global Ollama thinking mode.

    Returning None intentionally leaves the model/server default unchanged.
    """
    normalized_role = role.strip().casefold()
    if normalized_role not in {"intent", "mechanics", "extraction", "narrative"}:
        raise ValueError(f"unsupported Ollama provider role: {role}")

    names = (
        f"CAMPAIGN_MANAGER_LLM_{normalized_role.upper()}_THINK",
        "CAMPAIGN_MANAGER_REAL_LLM_THINK",
        "CAMPAIGN_MANAGER_OLLAMA_THINK",
    )
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"{name} must be a boolean (true/false)")
    return None
