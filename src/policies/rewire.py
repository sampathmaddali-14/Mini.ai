"""
Rewire policy — knowledge graph maintenance.

Two modes:
  - resolve: triggered by curation's contradiction flag. Supersedes old fact,
    links new fact. Both retained.
  - sweep: hourly heartbeat. Extracts entity co-occurrences from recent episodes
    and adds graph edges in Kuzu.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
import itertools
import os

import httpx

from ..core.policy_base import CognitivePolicy, PolicyContext, PolicyResult


KUZU_URL = os.getenv("KUZU_URL", "http://kuzu:8000")
KUZU_TIMEOUT = float(os.getenv("KUZU_TIMEOUT", "5"))


class KuzuClient:
    """Minimal Cypher-like client for the Kuzu REST wrapper."""

    def __init__(self, base: str = KUZU_URL):
        self._base = base.rstrip("/")
        self._client = httpx.Client(timeout=KUZU_TIMEOUT)

    def query(self, cypher: str, params: Optional[dict] = None) -> list[dict]:
        r = self._client.post(
            f"{self._base}/cypher",
            json={"query": cypher, "parameters": params or {}},
        )
        r.raise_for_status()
        return r.json().get("results", [])

    def close(self) -> None:
        self._client.close()


class RewirePolicy(CognitivePolicy):
    name = "rewire"

    def __init__(self, kuzu: Optional[KuzuClient] = None):
        self.kuzu = kuzu or KuzuClient()

    def run(self, ctx: PolicyContext, *, mode: str = "sweep", **kwargs: Any) -> PolicyResult:
        if mode == "resolve":
            return self._resolve(ctx, **kwargs)
        if mode == "sweep":
            return self._sweep(ctx, **kwargs)
        return self._result(ok=False, errors=[f"unknown mode: {mode}"])

    # ---- resolve: contradiction handling ----

    def _resolve(self, ctx: PolicyContext, *, old_memory_id: str,
                 new_memory_id: str, reason: str = "contradiction", **_) -> PolicyResult:
        if ctx.dry_run:
            ctx.log(self.name, mode="resolve", old=old_memory_id, new=new_memory_id,
                    reason=reason, dry=True)
            return self._result(ok=True, mode="resolve", supersessions=1)

        try:
            # Mark old memory as superseded in MemOS
            ctx.memory.update_status(old_memory_id, "superseded")

            # Add supersession edge in Kuzu
            self.kuzu.query(
                """
                MERGE (old:Memory {id: $old_id})
                MERGE (new:Memory {id: $new_id})
                MERGE (new)-[r:SUPERSEDES]->(old)
                ON CREATE SET r.reason = $reason, r.ts = $ts
                """,
                {
                    "old_id": old_memory_id,
                    "new_id": new_memory_id,
                    "reason": reason,
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
            )
            ctx.log(self.name, mode="resolve", old=old_memory_id,
                    new=new_memory_id, reason=reason, ok=True)
            return self._result(ok=True, mode="resolve", supersessions=1)
        except Exception as e:
            ctx.log(self.name, mode="resolve", error=str(e), ok=False)
            return self._result(ok=False, errors=[str(e)])

    # ---- sweep: co-occurrence edges ----

    def _sweep(self, ctx: PolicyContext, *, window_hours: int = 1, **_) -> PolicyResult:
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

        # Pull recent episodes with entities
        recent = ctx.memory.recent(tier="episodic", limit=200)
        recent = [m for m in recent if m.timestamp >= since and m.entities]

        edges_added = 0
        pairs_seen = 0
        for episode in recent:
            entities = list(set(episode.entities or []))
            for a, b in itertools.combinations(sorted(entities), 2):
                pairs_seen += 1
                if ctx.dry_run:
                    continue
                try:
                    self._upsert_cooccurrence(a, b, episode.id)
                    edges_added += 1
                except Exception as e:
                    ctx.logger.warning(f"edge upsert failed ({a}, {b}): {e}")

        ctx.log(self.name, mode="sweep", window_h=window_hours,
                episodes=len(recent), pairs_seen=pairs_seen,
                edges_added=edges_added)
        return self._result(
            ok=True, mode="sweep",
            edges_added=edges_added, pairs_seen=pairs_seen,
            episodes_scanned=len(recent),
        )

    def _upsert_cooccurrence(self, a: str, b: str, episode_id: str) -> None:
        self.kuzu.query(
            """
            MERGE (e1:Entity {name: $a})
            MERGE (e2:Entity {name: $b})
            MERGE (e1)-[r:CO_OCCURS_WITH]->(e2)
            ON CREATE SET r.weight = 1, r.sources = [$ep]
            ON MATCH  SET r.weight = r.weight + 1,
                          r.sources = CASE WHEN $ep IN r.sources THEN r.sources
                                           ELSE r.sources + $ep END
            """,
            {"a": a, "b": b, "ep": episode_id},
        )

    # ---- graph queries (for inspector + why-query) ----

    def path_between(self, ctx: PolicyContext, *, a: str, b: str,
                     max_hops: int = 4) -> list[dict]:
        """Support 'why A B' style queries."""
        return self.kuzu.query(
            f"""
            MATCH p = (x:Entity {{name: $a}})-[:CO_OCCURS_WITH*1..{max_hops}]-(y:Entity {{name: $b}})
            RETURN p LIMIT 1
            """,
            {"a": a, "b": b},
        )

    def orphan_entity_ids(self, ctx: PolicyContext, older_than_days: int = 7) -> list[str]:
        """Return entity nodes with degree 0 eligible for pruning handoff."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        res = self.kuzu.query(
            """
            MATCH (e:Entity)
            WHERE NOT (e)--() AND e.created_at < $cutoff
            RETURN e.name AS name
            """,
            {"cutoff": cutoff},
        )
        return [r["name"] for r in res]
