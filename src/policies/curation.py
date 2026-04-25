"""
Curation policy — the write-path filter.

Every candidate memory passes through here before being persisted. Decides
among: accept, reject, merge (into existing), supersede (contradicts existing).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, Optional
import json
import os

from ..core.policy_base import CognitivePolicy, PolicyContext, PolicyResult
from .salience import Candidate, ScoreBreakdown, score, DEFAULT_THRESHOLD


Decision = Literal["accept", "reject", "merge", "supersede"]


@dataclass
class CurationOutcome:
    decision: Decision
    salience: ScoreBreakdown
    memory_id: Optional[str] = None
    merge_target_id: Optional[str] = None
    supersedes_id: Optional[str] = None
    reason: str = ""


class CurationPolicy(CognitivePolicy):
    name = "curation"

    DEDUP_THRESHOLD = float(os.getenv("DEDUP_SIMILARITY_THRESHOLD", "0.92"))

    def run(self, ctx: PolicyContext, *, candidate: Candidate,
            tier: str = "episodic", **_: Any) -> PolicyResult:
        recent_ctx = ctx.memory.search(
            query=candidate.content, tier=tier, top_k=8, hide_superseded=True,
        )

        topic_count_7d = sum(
            1 for m in recent_ctx
            if any(e.lower() in m.content.lower() for e in candidate.entities)
        )

        prefs = ctx.memory.search(query="user preference", tier="semantic", top_k=10)
        known_prefs = [p.content for p in prefs]

        s = score(candidate, topic_count_7d=topic_count_7d, known_preferences=known_prefs)

        if not s.accept():
            outcome = CurationOutcome(
                decision="reject", salience=s,
                reason=f"salience {s.total} < threshold {DEFAULT_THRESHOLD}",
            )
            return self._emit(ctx, outcome, tier)

        dup = self._find_near_duplicate(candidate, recent_ctx)
        if dup is not None:
            outcome = CurationOutcome(
                decision="merge", salience=s, merge_target_id=dup.id,
                reason=f"near-duplicate of {dup.id}",
            )
            return self._emit(ctx, outcome, tier)

        if self._is_claim(candidate.content):
            contradicting_id = self._detect_contradiction(ctx, candidate, recent_ctx)
            if contradicting_id is not None:
                new_id = self._write(ctx, candidate, tier)
                outcome = CurationOutcome(
                    decision="supersede", salience=s,
                    memory_id=new_id, supersedes_id=contradicting_id,
                    reason=f"contradicts {contradicting_id}",
                )
                return self._emit(ctx, outcome, tier)

        new_id = self._write(ctx, candidate, tier)
        return self._emit(ctx, CurationOutcome(
            decision="accept", salience=s, memory_id=new_id, reason="salience pass",
        ), tier)

    # ---- helpers ----

    def _find_near_duplicate(self, candidate: Candidate, recent):
        """Token-overlap fallback until we wire MemOS embedding scores.
        Real impl: MemOS returns cosine similarity with each result."""
        cand_tokens = set(candidate.content.lower().split())
        if not cand_tokens:
            return None
        for m in recent:
            m_tokens = set(m.content.lower().split())
            if not m_tokens:
                continue
            jaccard = len(cand_tokens & m_tokens) / len(cand_tokens | m_tokens)
            if jaccard >= self.DEDUP_THRESHOLD:
                return m
        return None

    @staticmethod
    def _is_claim(text: str) -> bool:
        """Heuristic: claim-like content is worth contradiction-checking.
        Avoid spending LLM calls on questions and acks."""
        t = text.strip().lower()
        if not t or t.endswith("?"):
            return False
        noise = {"ok", "thanks", "yes", "no", "sure", "got it"}
        if t in noise:
            return False
        return len(t.split()) >= 5

    def _detect_contradiction(self, ctx: PolicyContext, candidate: Candidate,
                              recent) -> Optional[str]:
        if not recent:
            return None
        numbered = "\n".join(f"[{i}] id={m.id}: {m.content}" for i, m in enumerate(recent))
        prompt = (
            "You are a fact-consistency checker. Given a new statement and a list of "
            "existing memories, identify if the new statement directly contradicts any "
            "existing memory (not merely adds information or refines it).\n\n"
            f"NEW: {candidate.content}\n\nEXISTING:\n{numbered}\n\n"
            "Respond with JSON only: "
            '{"contradicts": true|false, "id": "<memory_id or null>", "reason": "<short>"}'
        )
        raw = ctx.llm.ask(prompt, max_tokens=200, expect_json=True)
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return None
        if data.get("contradicts") is True:
            return data.get("id")
        return None

    def _write(self, ctx: PolicyContext, candidate: Candidate, tier: str) -> str:
        if ctx.dry_run:
            return "dryrun-id"
        m = ctx.memory.add(
            content=candidate.content,
            tier=tier,
            entities=candidate.entities,
            user_override=candidate.user_override,
            source="curation",
        )
        return m.id

    def _emit(self, ctx: PolicyContext, outcome: CurationOutcome, tier: str) -> PolicyResult:
        ctx.log(
            self.name,
            decision=outcome.decision,
            salience=outcome.salience.total,
            tier=tier,
            memory_id=outcome.memory_id,
            merge_target=outcome.merge_target_id,
            supersedes=outcome.supersedes_id,
            reason=outcome.reason,
        )
        return self._result(
            ok=True,
            decision=outcome.decision,
            salience=outcome.salience.total,
            memory_id=outcome.memory_id,
            merge_target=outcome.merge_target_id,
            supersedes=outcome.supersedes_id,
        )
