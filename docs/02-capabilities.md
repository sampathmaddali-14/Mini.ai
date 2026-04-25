# Mini.ai — Capabilities

Each capability is tied to one of the six cognitive verbs. "MUST" items ship in v0.1. "SHOULD" items are Phase 2. "MAY" items are exploratory.

## 1. CREATE — generate new knowledge and skills

- **MUST** Capture every user-agent exchange as an episodic memory entry with timestamp, source, and raw content.
- **MUST** Detect when a successfully completed task has no matching skill, and generate a new skill (SKILL.md + executable code) for it.
- **MUST** Validate newly-generated skills via self-verification before adding to the skill library.
- **SHOULD** Tag new memories with automatically-extracted entities for downstream graph linking.
- **MAY** Propose skill creation to the user for sensitive categories before auto-adding.

## 2. CURATE — filter what enters memory

- **MUST** Apply a salience score to every candidate memory before writing. Reject items below threshold.
- **MUST** Detect near-duplicates at write time and merge rather than insert.
- **MUST** Flag contradictions at write time — any new fact inconsistent with an existing fact triggers the rewire pipeline.
- **SHOULD** Apply user-specific salience weights (preferences, recurring topics score higher).
- **SHOULD** Support explicit user override: "remember this" bypasses curation filter.

## 3. REFINE — improve what's already stored

- **MUST** Run a scheduled reflection pass (heartbeat-driven) that reviews recent episodes and extracts insights.
- **MUST** Update skill quality scores based on invocation outcomes (success / failure / user correction).
- **SHOULD** Deprecate skills that consistently fail or are superseded by better ones.
- **SHOULD** Refactor repeated episode patterns into semantic-memory generalizations.
- **MAY** Generate skill variants and A/B test them against each other.

## 4. REWIRE — restructure relationships

- **MUST** Maintain a knowledge graph of entities and relationships in Kuzu.
- **MUST** Add graph edges when new entity co-occurrences are detected in episodes.
- **MUST** On contradiction: mark old fact as superseded, link new fact, retain provenance for both.
- **SHOULD** Periodically run a graph-cleanup pass that removes orphan nodes and dead edges.
- **SHOULD** Support "why" queries — explain why two facts are linked via path traversal.

## 5. LEARN — consolidate experience into knowledge

- **MUST** Run a nightly consolidation job that summarizes the day's episodic memories into semantic memories.
- **MUST** Move high-confidence semantic memories into a "long-term" tier that is always retrievable.
- **SHOULD** Escalate the most stable, high-confidence knowledge to parametric memory via periodic LoRA fine-tuning. (Phase 2.)
- **SHOULD** Export consolidated knowledge as a portable snapshot (JSON / graph dump).
- **MAY** Import knowledge from external sources (documents, RSS, imported chat logs).

## 6. UNLEARN — forget cleanly

- **MUST** Apply decay scoring to all memories; memories below a threshold are eligible for deletion.
- **MUST** Support explicit user-triggered deletion by topic, entity, or time range, with tombstoning so superseded-but-needed context still resolves.
- **MUST** When a memory is deleted, cascade to its graph relationships.
- **SHOULD** Retain an audit log of deletions for recovery within a grace window.
- **SHOULD** Support selective "forget this conversation" requests.
- **MAY** Implement parametric unlearning via retention-controlled LoRA updates. (Research.)

## Cross-cutting capabilities

- **MUST** Run as a persistent daemon with a heartbeat scheduler — background jobs fire on schedule without user prompts.
- **MUST** Operate offline-capable for memory/skill ops; only reasoning calls go to a hosted LLM API.
- **MUST** Expose a conversational interface on at least one channel (CLI, Telegram, or local web UI).
- **MUST** Be deployable via `docker compose up` with no proprietary dependencies.
- **SHOULD** Provide a memory inspector UI for debugging and manual curation.
- **SHOULD** Emit structured logs for all cognitive policy firings (observability).

## Measurable targets for v0.1

| Capability | Target | How measured |
|---|---|---|
| Preference recall | 90% of preferences set in week 1 recalled unprompted by week 4 | Fixed eval set of 20 preferences |
| Skill generation | ≥3 auto-generated skills after 30 days of use | Skill library file count |
| Consolidation | Week-1 episodes summarized into semantic memory by day 14 | Manual audit |
| Pruning | ≥20% of week-1 episodic memories pruned by day 30 | Row counts before/after |
| Contradiction handling | ≥95% of injected contradictions correctly resolved | Synthetic test set |
| Autonomy | ≥24hr continuous runtime, heartbeat jobs succeed ≥99% | Runtime logs |
