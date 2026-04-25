"""
Reflection policy — every 30 minutes.

1. Score recent skill invocations (EWMA quality per skill).
2. Deprecate consistently-failing skills.
3. Extract insights from recent episodes (LLM pattern detection).
4. Route insights through curation before writing.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import json
import os
import sqlite3
from pathlib import Path

from ..core.policy_base import CognitivePolicy, PolicyContext, PolicyResult
from .salience import Candidate
from .curation import CurationPolicy


SKILL_QUALITY_DB = Path(os.getenv("SKILL_QUALITY_DB", "/var/lib/openclaw/skill_quality.db"))
EWMA_ALPHA = float(os.getenv("SKILL_EWMA_ALPHA", "0.2"))
DEPRECATE_THRESHOLD = float(os.getenv("SKILL_DEPRECATE_THRESHOLD", "0.3"))
DEPRECATE_MIN_INVOCATIONS = int(os.getenv("SKILL_DEPRECATE_MIN_N", "10"))


@dataclass
class SkillInvocation:
    skill: str
    ts: datetime
    outcome: str        # success | failure | user_correction
    duration_ms: int


class SkillQualityStore:
    """Tiny SQLite store for skill quality scores. OpenClaw logs invocations here;
    reflection reads + writes."""

    def __init__(self, path: Path = SKILL_QUALITY_DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS invocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    duration_ms INTEGER
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS skill_quality (
                    skill TEXT PRIMARY KEY,
                    quality REAL NOT NULL DEFAULT 0.5,
                    invocations INTEGER NOT NULL DEFAULT 0,
                    failures_7d INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    updated_at TEXT NOT NULL
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_inv_ts ON invocations(ts)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_inv_skill ON invocations(skill)")

    def record_invocation(self, inv: SkillInvocation) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO invocations(skill, ts, outcome, duration_ms) VALUES (?, ?, ?, ?)",
                (inv.skill, inv.ts.isoformat(), inv.outcome, inv.duration_ms),
            )

    def recent_invocations(self, since: datetime) -> list[SkillInvocation]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT skill, ts, outcome, duration_ms FROM invocations WHERE ts >= ?",
                (since.isoformat(),),
            )
            return [
                SkillInvocation(
                    skill=row[0],
                    ts=datetime.fromisoformat(row[1]),
                    outcome=row[2],
                    duration_ms=row[3] or 0,
                )
                for row in cur.fetchall()
            ]

    def update_quality(self, skill: str, outcome: str) -> tuple[float, int]:
        with self._conn() as c:
            row = c.execute(
                "SELECT quality, invocations FROM skill_quality WHERE skill = ?", (skill,),
            ).fetchone()
            current_q = row[0] if row else 0.5
            current_n = row[1] if row else 0
            success = 1.0 if outcome == "success" else 0.0
            new_q = EWMA_ALPHA * success + (1 - EWMA_ALPHA) * current_q
            new_n = current_n + 1
            c.execute(
                """
                INSERT INTO skill_quality(skill, quality, invocations, updated_at)
                    VALUES (?, ?, ?, ?)
                ON CONFLICT(skill) DO UPDATE SET
                    quality = excluded.quality,
                    invocations = excluded.invocations,
                    updated_at = excluded.updated_at
                """,
                (skill, round(new_q, 4), new_n, datetime.now(timezone.utc).isoformat()),
            )
            return new_q, new_n

    def deprecate(self, skill: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE skill_quality SET status = 'deprecated', updated_at = ? WHERE skill = ?",
                (datetime.now(timezone.utc).isoformat(), skill),
            )

    def deprecation_candidates(self, since: datetime) -> list[tuple[str, float, int]]:
        with self._conn() as c:
            cur = c.execute(
                """
                SELECT sq.skill, sq.quality,
                       (SELECT COUNT(*) FROM invocations i
                        WHERE i.skill = sq.skill AND i.ts >= ?) AS recent_n
                FROM skill_quality sq
                WHERE sq.status = 'active'
                  AND sq.quality < ?
                  AND (SELECT COUNT(*) FROM invocations i
                       WHERE i.skill = sq.skill AND i.ts >= ?) >= ?
                """,
                (since.isoformat(), DEPRECATE_THRESHOLD,
                 since.isoformat(), DEPRECATE_MIN_INVOCATIONS),
            )
            return cur.fetchall()


class ReflectionPolicy(CognitivePolicy):
    name = "reflection"

    def __init__(self, quality_store: Optional[SkillQualityStore] = None):
        self.store = quality_store or SkillQualityStore()

    def run(self, ctx: PolicyContext, *, window_minutes: int = 30, **_: Any) -> PolicyResult:
        window_since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

        # 1. Score recent skill invocations
        invocations = self.store.recent_invocations(window_since)
        scored = 0
        for inv in invocations:
            self.store.update_quality(inv.skill, inv.outcome)
            scored += 1

        # 2. Deprecate consistently-failing skills
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        deprecations = []
        for skill, quality, n in self.store.deprecation_candidates(week_ago):
            if not ctx.dry_run:
                self.store.deprecate(skill)
            deprecations.append({"skill": skill, "quality": quality, "n": n})

        # 3. Extract insights from recent episodes
        insights_written = self._extract_insights(ctx, window_since)

        ctx.log(
            self.name,
            window_m=window_minutes,
            skills_scored=scored,
            deprecated=len(deprecations),
            deprecations=deprecations,
            insights_written=insights_written,
        )
        return self._result(
            ok=True, skills_scored=scored,
            deprecated=len(deprecations),
            insights_written=insights_written,
        )

    def _extract_insights(self, ctx: PolicyContext, since: datetime) -> int:
        recent = ctx.memory.recent(tier="episodic", limit=30)
        recent = [m for m in recent
                  if m.timestamp >= since and m.source != "reflection"]
        if len(recent) < 3:
            return 0

        numbered = "\n".join(f"- {m.content}" for m in recent[:30])
        prompt = (
            "Below are recent episodic memories from a personal AI assistant. "
            "Identify 0 to 3 durable semantic claims that capture patterns, preferences, "
            "or facts about the user that would be useful for future conversations. "
            "Each claim must be independently useful without this context. "
            "Omit transient details. If nothing durable is present, return [].\n\n"
            f"EPISODES:\n{numbered}\n\n"
            "Respond with JSON only: "
            '[{"claim": "<text>", "confidence": 0.0-1.0}]'
        )
        raw = ctx.llm.ask(prompt, max_tokens=500, expect_json=True)
        try:
            insights = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return 0

        curation = CurationPolicy()
        written = 0
        for ins in insights:
            claim = (ins.get("claim") or "").strip()
            if not claim or len(claim) < 10:
                continue
            conf = float(ins.get("confidence", 0.6))
            if conf < 0.5:
                continue
            candidate = Candidate(
                content=claim,
                timestamp=datetime.now(timezone.utc),
                entities=[],
            )
            # Reflection-sourced insights write to semantic tier via curation
            result = curation.run(ctx, candidate=candidate, tier="semantic")
            if result.summary.get("decision") in ("accept", "merge"):
                written += 1
        return written
