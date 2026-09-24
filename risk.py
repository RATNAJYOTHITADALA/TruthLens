"""Deterministic server-side risk indicators for submitted claims."""

from __future__ import annotations


SENSATIONAL_PHRASES = ("breaking", "shocking", "share before deleted")


def assess_risk(claim_text: str, source_url: str | None = None) -> dict:
    """Calculate base flags, score, and high-risk state from claim input."""
    normalized_text = " ".join(claim_text.casefold().split())
    flags: list[str] = []

    if any(phrase in normalized_text for phrase in SENSATIONAL_PHRASES):
        flags.append("sensational")

    alphabetic = [character for character in claim_text if character.isalpha()]
    if alphabetic and sum(character.isupper() for character in alphabetic) / len(alphabetic) > 0.5:
        flags.append("shouting")

    if not source_url or not source_url.strip():
        flags.append("unsourced")

    score = len(flags)
    return {
        "risk_flags": flags,
        "risk_score": score,
        "high_risk": score >= 2,
    }
