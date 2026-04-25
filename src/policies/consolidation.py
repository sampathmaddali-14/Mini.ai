"""
Consolidation policy — nightly, 03:00 local time.

Summarizes yesterday's episodic memories into durable semantic memories.
The "sleep" analog. The most important cognitive policy — where raw experience
becomes knowledge.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import json
import os
from collections import defaultdict

from ..core.policy_base import CognitivePolicy, PolicyContext, PolicyResult
from .salience import Candidate
from .curation import CurationPolicy


LONG_TERM_CONF_THRESHOLD = float(os.getenv("LONG_TERM_CONF_THRESHOLD", "0.8"))
LONG_TERM_AGE_DAYS = int(os.getenv("LONG_TERM_AGE_DAYS", "14"))
DEMOTE_UNUSED_DAYS = int(os.getenv("DEMOTE_UNUSED_DAYS", "90"))


class ConsolidationPolicy(CognitivePolicy):
    name = "consolidation"

    def run(self, ctx: PolicyContext, *,
            date: Optional[str] = None, **_: Any) -> PolicyResult:
        target_date = self._parse_date(date)
        start = target_date.replace(hour=0, minute=0, second=0, microsecond=0,
                                    tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        # 1. Pull yesterday's episodes
        episodes = self._fetch_episodes(ctx, start, end)
        if len(episodes) < 3:
            ctx.log(self.name, date=target_date.date().isoformat(),
                    episodes=len(episodes), skipped="not_enough_episodes")
            return self._result(ok=True, episodes=len(episodes),
                                skipped="not_enough_episodes")

        # 2. Cluster by topic (entity-overlap clustering as baseline)
        clusters = self._cluster_by_entities(episodes)

        # 3. Summarize each cluster into semantic claims via curation
        semantic_written = 0
        curation = CurationPolicy()
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            claims = self._summarize_cluster(ctx, cluster)
            for claim in claims:
                conf = self._score_confidence(
                    cluster_size=len(cluster),
                    claim_data=claim,
                )
                candidate = Candidate(
                    content=claim["text"],
                    timestamp=datetime.now(timezone.utc),
                    entities=claim.get("entities", []),
                )
                result = curation.run(ctx, candidate=candidate, tier="semantic")
                if result.summary.get("decision") in ("accept", "merge"):
                    semantic_written += 1
                    if not ctx.dry_run:
                        self._tag_consolidated(
                            ctx,
                            [m.id for m in cluster],
                            result.summary.get("memory_id"),
                            conf,
                        )

        # 4. Promote high-confidence, stable semantic memories to long-term tier
        promoted = self._promote_to_long_term(ctx)

        # 5. Demote long-unused long-term memories back to semantic
        demoted = self._demote_stale(ctx)

        ctx.log(
            self.name, date=target_date.date().isoformat(),
            episodes=len(episodes), clusters=len(clusters),
            semantic_written=semantic_written,
            promoted=promoted, demoted=demoted,
        )
        return self._result(
            ok=True,
            episodes=len(episodes), clusters=len(clusters),
            semantic_written=semantic_written,
            promoted=promoted, demoted=demoted,
        )

    # ---- helpers ----

    @staticmethod
    def _parse_date(date: Optional[str]) -> datetime:
        if date:
            return datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        # Default: yesterday
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return today - timedelta(days=1)

    def _fetch_episodes(self, ctx: PolicyContext, start: datetime, end: datetime):
        # Pull recent episodic, filter by timestamp range.
        # Real MemOS endpoint should accept time-range params; we do it client-side here.
        raw = ctx.memory.recent(tier="episodic", limit=500)
        return [
            m for m in raw
            if start <= m.timestamp < end
            and m.source != "reflection"
            and m.source != "consolidation"
        ]

    def _cluster_by_entities(self, episodes) -> list[list]:
        """Greedy clustering by shared-entity overlap. Simple and deterministic.
        Upgrade to HDBSCAN on embeddings in Phase 2."""
        clusters: list[list] = []
        assigned = set()
        for i, ep in enumerate(episodes):
            if i in assigned:
                continue
            cluster = [ep]
            ep_entities = set(e.lower() for e in (ep.entities or []))
            assigned.add(i)
            if not ep_entities:
                clusters.append(cluster)
                continue
            for j in range(i + 1, len(episodes)):
                if j in assigned:
                    continue
                other = episodes[j]
                other_entities = set(e.lower() for e in (other.entities or []))
                if not other_entities:
                    continue
                overlap = ep_entities & other_entities
                if overlap:
                    cluster.append(other)
                    assigned.add(j)
            clusters.append(cluster)
        return clusters

    def _summarize_cluster(self, ctx: PolicyContext, cluster) -> list[dict]:
        """Ask the LLM for 1-2 durable claims from a cluster."""
        bullets = "\n".join(f"- {m.content}" for m in cluster[:20])
        prompt = (
            f"Here are {len(cluster)} related episodic memories from a personal AI "
            "assistant's user. Produce 1 or 2 durable semantic claims that capture "
            "what matters for future reference. Each claim must be independently useful. "
            "Omit transient details (times, one-off context). If nothing durable is "
            "present, return [].\n\n"
            f"EPISODES:\n{bullets}\n\n"
            "Respond with JSON only: "
            '[{"text": "<claim>", "entities": ["..."], "internal_agreement": 0.0-1.0}]'
        )
        raw = ctx.llm.ask(prompt, max_tokens=600, expect_json=True)
        try:
            claims = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
        return [c for c in claims if isinstance(c, dict) and c.get("text")]

    @staticmethod
    def _score_confidence(*, cluster_size: int, claim_data: dict) -> float:
        agreement = float(claim_data.get("internal_agreement", 0.6))
        size_boost = min(0.3, (cluster_size - 2) * 0.05)
        return min(1.0, agreement + size_boost)

    def _tag_consolidated(self, ctx: PolicyContext, episode_ids: list[str],
                          semantic_id: Optional[str], confidence: float) -> None:
        """Tag source episodes so we don't reconsolidate them. Placeholder until
        MemOS exposes a tag endpoint."""
        if not semantic_id:
            return
        # A thin patch would go here. For now we rely on the timestamp filter to
        # prevent reconsolidation (episodes from yesterday don't get re-processed
        # since consolidation runs per-date).

    def _promote_to_long_term(self, ctx: PolicyContext) -> int:
        """Stable, high-confidence, accessed-enough semantic memories become long-term."""
        # Conservative placeholder: return 0 until MemOS exposes tier transitions.
        # The policy is defined in the SKILL.md; wiring is a Phase-1b task.
        return 0

    def _demote_stale(self, ctx: PolicyContext) -> int:
        """Long-term memories untouched for DEMOTE_UNUSED_DAYS days get demoted."""
        return 0
