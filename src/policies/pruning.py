"""
Pruning policy — weekly, Sundays 03:30.

Decay-based deletion. Cascades to graph edges. Writes tombstones for recovery.
Rate-limited to never delete more than N% of total memory in one pass.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import json
import math
import os
import sqlite3
from pathlib import Path

from ..core.policy_base import CognitivePolicy, PolicyContext, PolicyResult
from .rewire import KuzuClient


TOMBSTONE_DB = Path(os.getenv("TOMBSTONE_DB", "/var/lib/openclaw/tombstones.db"))
HALF_LIFE_EPISODIC = int(os.getenv("DECAY_HALF_LIFE_DAYS_EPISODIC", "14"))
HALF_LIFE_SEMANTIC = int(os.getenv("DECAY_HALF_LIFE_DAYS_SEMANTIC", "180"))
DELETE_THRESHOLD = float(os.getenv("DECAY_DELETE_THRESHOLD", "0.85"))
MAX_DELETE_PCT = float(os.getenv("PRUNING_MAX_DELETE_PCT", "10"))
GRACE_DAYS = int(os.getenv("TOMBSTONE_GRACE_DAYS", "7"))


class TombstoneStore:
    """Records deletions so user can undelete within the grace window."""

    def __init__(self, path: Path = TOMBSTONE_DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS tombstones (
                    id TEXT PRIMARY KEY,
                    deleted_at TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    tier TEXT,
                    content TEXT,
                    entities TEXT,
                    expires_at TEXT NOT NULL
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_tomb_expires ON tombstones(expires_at)")

    def record(self, *, memory_id: str, reason: str, tier: str,
               content: str, entities: list[str]) -> None:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=GRACE_DAYS)
        with self._conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO tombstones(id, deleted_at, reason, tier,
                    content, entities, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (memory_id, now.isoformat(), reason, tier, content,
                 json.dumps(entities), expires.isoformat()),
            )

    def get(self, memory_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute(
                "SELECT id, deleted_at, reason, tier, content, entities, expires_at "
                "FROM tombstones WHERE id = ?", (memory_id,),
            ).fetchone()
        if not row:
            return None
        expires = datetime.fromisoformat(row[6])
        if expires < datetime.now(timezone.utc):
            return {"id": row[0], "expired": True}
        return {
            "id": row[0], "deleted_at": row[1], "reason": row[2], "tier": row[3],
            "content": row[4], "entities": json.loads(row[5] or "[]"),
            "expires_at": row[6], "expired": False,
        }

    def compact_expired(self) -> int:
        """Purge content from tombstones past their grace window. Keep the ID row
        for audit, but drop the recovery payload."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            cur = c.execute(
                "UPDATE tombstones SET content = NULL, entities = NULL "
                "WHERE expires_at < ? AND content IS NOT NULL",
                (now,),
            )
            return cur.rowcount


def decay_score(
    *,
    age_days: float,
    half_life_days: int,
    access_count_30d: int = 0,
    incoming_edges: int = 0,
    user_marked: bool = False,
    long_term: bool = False,
) -> float:
    """
    decay_score = 1 - exp(-age * ln2 / half_life) * (1 + access_bonus)

    long_term memories short-circuit to 0 (exempt).
    user_marked and graph-connected memories get a doubled half-life (stickier).
    """
    if long_term:
        return 0.0
    if user_marked:
        half_life_days = half_life_days * 2
    if incoming_edges > 3:
        half_life_days = int(half_life_days * 1.5)
    access_bonus = min(0.5, 0.05 * max(0, access_count_30d))
    base = 1 - math.exp(-age_days * math.log(2) / max(1, half_life_days))
    score = base * (1 + access_bonus)
    return min(1.0, max(0.0, score))


class PruningPolicy(CognitivePolicy):
    name = "pruning"

    def __init__(self, tombstones: Optional[TombstoneStore] = None,
                 kuzu: Optional[KuzuClient] = None):
        self.tombstones = tombstones or TombstoneStore()
        self.kuzu = kuzu or KuzuClient()

    def run(self, ctx: PolicyContext, **_: Any) -> PolicyResult:
        now = datetime.now(timezone.utc)
        total = ctx.memory.count()
        max_delete = int(total * MAX_DELETE_PCT / 100.0)

        candidates = self._collect_candidates(ctx, now)
        to_delete = candidates[:max_delete]
        skipped_rate_limited = len(candidates) - len(to_delete)

        edges_removed = 0
        deleted = 0
        for mem in to_delete:
            try:
                if not ctx.dry_run:
                    self.tombstones.record(
                        memory_id=mem.id, reason="decay",
                        tier=mem.tier, content=mem.content,
                        entities=mem.entities or [],
                    )
                    edges_removed += self._cascade_graph(mem.id)
                    ctx.memory.delete(mem.id, reason="decay")
                deleted += 1
            except Exception as e:
                ctx.logger.warning(f"prune failed for {mem.id}: {e}")

        # Compact expired tombstones
        compacted = 0
        if not ctx.dry_run:
            compacted = self.tombstones.compact_expired()

        ctx.log(
            self.name, total=total, max_delete=max_delete,
            candidates=len(candidates), deleted=deleted,
            edges_removed=edges_removed,
            rate_limited=skipped_rate_limited,
            tombstones_compacted=compacted,
        )
        return self._result(
            ok=True, total=total, deleted=deleted,
            edges_removed=edges_removed,
            rate_limited=skipped_rate_limited,
        )

    def _collect_candidates(self, ctx: PolicyContext, now: datetime) -> list:
        """Scan memory tiers, compute decay, return sorted (highest decay first)."""
        candidates = []
        for tier, half_life in (("episodic", HALF_LIFE_EPISODIC),
                                ("semantic", HALF_LIFE_SEMANTIC)):
            rows = ctx.memory.recent(tier=tier, limit=5000)
            for m in rows:
                if m.status == "superseded":
                    continue
                age_days = (now - m.timestamp).total_seconds() / 86400.0
                # Long-term exemption: inferred from tier name
                long_term = (tier == "long_term")
                score = decay_score(
                    age_days=age_days,
                    half_life_days=half_life,
                    long_term=long_term,
                )
                if score >= DELETE_THRESHOLD:
                    candidates.append(m)
        return candidates

    def _cascade_graph(self, memory_id: str) -> int:
        """Remove graph edges incident to this memory. Return edge count removed."""
        try:
            res = self.kuzu.query(
                """
                MATCH (m:Memory {id: $id})-[r]-()
                WITH count(r) AS n
                DETACH DELETE (m:Memory {id: $id})
                RETURN n
                """,
                {"id": memory_id},
            )
            return int(res[0].get("n", 0)) if res else 0
        except Exception:
            return 0
