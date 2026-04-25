"""
Salience scoring for the curation policy.

Every memory that wants to persist passes through score(). The score is a
weighted sum of five factors, each in [0, 1]. The weights are tunable via env.

This module is intentionally small and LLM-free for the common path. Only the
entity extraction step may hit an LLM, and it's cached per-turn.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
import math
import os
import re


# ---- Configuration (env-driven) ----

W_RECENCY = float(os.getenv("SALIENCE_W_RECENCY", "0.15"))
W_ENTITY = float(os.getenv("SALIENCE_W_ENTITY", "0.25"))
W_REPETITION = float(os.getenv("SALIENCE_W_REPETITION", "0.20"))
W_PREFERENCE = float(os.getenv("SALIENCE_W_PREFERENCE", "0.20"))
W_MARKERS = float(os.getenv("SALIENCE_W_MARKERS", "0.20"))

DEFAULT_THRESHOLD = float(os.getenv("SALIENCE_THRESHOLD", "0.3"))

# Rough regex for decisional / preferential markers. Kept conservative; we'd
# rather miss a marker than over-boost.
_MARKER_PATTERNS = [
    r"\bI (want|need|prefer|decided|chose|hate|love|like|dislike)\b",
    r"\bmy (preference|favorite|goal|plan)\b",
    r"\bremember (this|that)\b",
    r"\bnever (again|do this)\b",
    r"\balways (do|prefer)\b",
]
_MARKER_RE = re.compile("|".join(_MARKER_PATTERNS), re.IGNORECASE)


# ---- Data types ----

@dataclass
class Candidate:
    content: str
    timestamp: datetime
    entities: list[str]
    user_override: bool = False  # "remember this"

@dataclass
class ScoreBreakdown:
    recency: float
    entity: float
    repetition: float
    preference: float
    markers: float
    total: float

    def accept(self, threshold: float = DEFAULT_THRESHOLD) -> bool:
        return self.total >= threshold


# ---- Scoring ----

def _recency(ts: datetime, now: Optional[datetime] = None) -> float:
    """Linear decay over 24h, floored at 0.1."""
    now = now or datetime.now(timezone.utc)
    age_hours = max(0.0, (now - ts).total_seconds() / 3600.0)
    if age_hours >= 24:
        return 0.1
    return max(0.1, 1.0 - (age_hours / 24.0) * 0.9)


def _entity_density(entities: list[str], content: str) -> float:
    """Entities per token, normalized. Dense = more retrievable later."""
    tokens = max(1, len(content.split()))
    raw = len(entities) / tokens
    # Typical dense prose: ~1 entity per 10-20 tokens => 0.05-0.1
    # Map [0, 0.1] -> [0, 1]. Clamp above.
    return min(1.0, raw * 10.0)


def _repetition(topic_count_7d: int) -> float:
    """Log-saturating curve. First mention ~ 0.0, 5 mentions ~ 0.7, 20+ -> 1.0."""
    if topic_count_7d <= 1:
        return 0.0
    return min(1.0, math.log1p(topic_count_7d - 1) / math.log(20))


def _preference_match(content: str, known_preferences: Iterable[str]) -> float:
    """Fraction of known preference keywords present in content. Cheap baseline.
    Real implementation should use embedding similarity. Keep this LLM-free here.
    """
    if not content:
        return 0.0
    lower = content.lower()
    hits = sum(1 for p in known_preferences if p.lower() in lower)
    return min(1.0, hits / 3.0)  # 3 hits = full score


def _markers(content: str) -> float:
    """Presence of decisional / preferential markers."""
    matches = _MARKER_RE.findall(content or "")
    if not matches:
        return 0.0
    # 1 match -> 0.6, 2 -> 0.85, 3+ -> 1.0
    return min(1.0, 0.6 + 0.25 * (len(matches) - 1))


def score(
    candidate: Candidate,
    topic_count_7d: int = 0,
    known_preferences: Iterable[str] = (),
    now: Optional[datetime] = None,
) -> ScoreBreakdown:
    """Compute salience score for a candidate memory."""
    if candidate.user_override:
        # "Remember this" bypasses scoring. Still return breakdown for logging.
        return ScoreBreakdown(1.0, 1.0, 1.0, 1.0, 1.0, 1.0)

    r = _recency(candidate.timestamp, now=now)
    e = _entity_density(candidate.entities, candidate.content)
    rep = _repetition(topic_count_7d)
    p = _preference_match(candidate.content, known_preferences)
    m = _markers(candidate.content)

    total = (
        W_RECENCY * r
        + W_ENTITY * e
        + W_REPETITION * rep
        + W_PREFERENCE * p
        + W_MARKERS * m
    )
    return ScoreBreakdown(r, e, rep, p, m, round(total, 4))


# ---- Quick self-check ----

if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    c = Candidate(
        content="I decided I prefer Docker Compose over Kubernetes for personal projects.",
        timestamp=now - timedelta(minutes=5),
        entities=["Docker Compose", "Kubernetes"],
    )
    s = score(c, topic_count_7d=3, known_preferences=["docker", "minimal infra"])
    print(f"Score: {s.total}  | accept={s.accept()}")
    print(f"  recency={s.recency:.2f} entity={s.entity:.2f} rep={s.repetition:.2f} "
          f"pref={s.preference:.2f} markers={s.markers:.2f}")
