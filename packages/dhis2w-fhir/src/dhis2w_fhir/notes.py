"""Human-facing note formatting shared by every emitter and the service layer."""

from __future__ import annotations


def aggregate_note(message: str, subjects: list[str], sample_size: int = 5) -> str:
    """One loud note for many subjects: message, a capped sample, and the remainder count."""
    sample = ", ".join(subjects[:sample_size])
    remainder = len(subjects) - sample_size
    return f"{message}: {sample}" + (f" and {remainder} more" if remainder > 0 else "")
