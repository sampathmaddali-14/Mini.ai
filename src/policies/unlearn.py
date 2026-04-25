"""
Unlearn policy — on-demand deletion.

Triggered by the user ("forget X") or by a policy. Unlike pruning (automatic,
decay-based), unlearn is explicit and scope-targeted.

Scope types: topic | entity | time_range | memory_id
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional
import json
import os

from ..core.policy_base import CognitivePolicy, PolicyContext, PolicyResult
from .pruning import TombstoneStore
from .rewire import KuzuClient


ScopeType = Literal["topic", "entity", "time_range", "memory_id"]
CONFIRM_THRESHOLD = int(os.getenv("UNLEARN_CONFIRM_THRESHOLD", "10"))


@dataclass
class UnlearnScope:
    type: ScopeType
    value: Any          # str for topic/entity/memory_id; dict {from, to} for time_range


class UnlearnPolicy(CognitivePolicy):
    name = "unlearn"

    def __init__(self, tombstones: Optional[TombstoneStore] = None,
                 kuzu: Optional[KuzuClient] = None):
        self.tombstones = tombstones or TombstoneStore()
        self.kuzu = kuzu or KuzuClient()

    def run(self, ctx: PolicyContext, *, scope: dict,
            confirmed: bool = False, **_: Any) -> PolicyResult:
        s = UnlearnScope(type=scope["type"], value=scope["value"])

        # 1. Resolve scope to matching memory IDs
        matches = self._resolve(ctx, s)

        # 2. Confirmation gate for large deletions
        if len(matches) > CONFIRM_THRESHOLD and not confirmed:
            ctx.log(self.name, scope=scope, matched=len(matches),
                    status="awaiting_confirmation")
            preview = [{"id": m.id, "content": m.content[:80]} for m in matches[:5]]
            return self._result(
                ok=True,
                status="awaiting_confirmation",
                matched=len(matches),
                preview=preview,
            )

        # 3. Cascade: tombstone + remove graph edges + delete memory
        edges_removed = 0
        deleted = 0
        orphaned_entities = []
        for m in matches:
            try:
                if not ctx.dry_run:
                    self.tombstones.record(
                        memory_id=m.id, reason="unlearn",
                        tier=m.tier, content=m.content,
                        entities=m.entities or [],
                    )
                    edges_removed += self._cascade_graph(m.id)
                    ctx.memory.delete(m.id, reason="unlearn")
                deleted += 1
            except Exception as e:
                ctx.logger.warning(f"unlearn failed for {m.id}: {e}")

        # 4. Entity cleanup — if scope was an entity, check if entity node is now orphaned
        if s.type == "entity":
            orphaned_entities = self._cleanup_entity_if_orphaned(s.value, ctx.dry_run)

        ctx.log(
            self.name, scope=scope, confirmed=confirmed,
            matched=len(matches), deleted=deleted,
            edges_removed=edges_removed,
            orphaned_entities=orphaned_entities,
        )
        return self._result(
            ok=True, matched=len(matches), deleted=deleted,
            edges_removed=edges_removed,
            orphaned_entities=orphaned_entities,
        )

    # ---- scope resolution ----

    def _resolve(self, ctx: PolicyContext, scope: UnlearnScope):
        if scope.type == "memory_id":
            try:
                return [ctx.memory.get(str(scope.value))]
            except Exception:
                return []

        if scope.type == "topic":
            return ctx.memory.search(
                query=str(scope.value), top_k=200, hide_superseded=False,
            )

        if scope.type == "entity":
            # All memories whose entities include the given name (case-insensitive).
            # Baseline: client-side filter on recent pull. Upgrade to MemOS
            # entity-index query once available.
            entity = str(scope.value).lower()
            all_memories = (
                ctx.memory.recent(tier="episodic", limit=5000)
                + ctx.memory.recent(tier="semantic", limit=2000)
            )
            return [
                m for m in all_memories
                if m.entities and any(e.lower() == entity for e in m.entities)
            ]

        if scope.type == "time_range":
            rng = scope.value or {}
            start = self._parse_ts(rng.get("from"))
            end = self._parse_ts(rng.get("to"))
            all_memories = (
                ctx.memory.recent(tier="episodic", limit=5000)
                + ctx.memory.recent(tier="semantic", limit=2000)
            )
            return [m for m in all_memories if start <= m.timestamp <= end]

        return []

    @staticmethod
    def _parse_ts(v: Any) -> datetime:
        if not v:
            return datetime.now(timezone.utc) - timedelta(days=365 * 10)
        if isinstance(v, datetime):
            return v
        return datetime.fromisoformat(str(v)).replace(
            tzinfo=timezone.utc if "T" in str(v) and "+" not in str(v) else None,
        )

    # ---- cascade ----

    def _cascade_graph(self, memory_id: str) -> int:
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

    def _cleanup_entity_if_orphaned(self, entity_name: str, dry_run: bool) -> list[str]:
        """If no remaining memories reference this entity, delete the entity node."""
        if dry_run:
            return []
        try:
            # Check degree
            deg = self.kuzu.query(
                """
                MATCH (e:Entity {name: $name})
                RETURN size((e)--()) AS degree
                """,
                {"name": entity_name},
            )
            if deg and int(deg[0].get("degree", 0)) == 0:
                self.kuzu.query(
                    "MATCH (e:Entity {name: $name}) DELETE e",
                    {"name": entity_name},
                )
                return [entity_name]
        except Exception:
            pass
        return []

    # ---- recovery ----

    def undelete(self, ctx: PolicyContext, *, memory_id: str) -> PolicyResult:
        tomb = self.tombstones.get(memory_id)
        if not tomb:
            return self._result(ok=False, errors=[f"no tombstone for {memory_id}"])
        if tomb.get("expired"):
            return self._result(ok=False, errors=[f"tombstone for {memory_id} expired past grace window"])
        if ctx.dry_run:
            return self._result(ok=True, restored=memory_id, dry=True)
        restored = ctx.memory.add(
            content=tomb["content"],
            tier=tomb["tier"],
            entities=tomb.get("entities", []),
            source="undelete",
        )
        ctx.log(self.name, action="undelete", original_id=memory_id, new_id=restored.id)
        return self._result(ok=True, original_id=memory_id, new_id=restored.id)
