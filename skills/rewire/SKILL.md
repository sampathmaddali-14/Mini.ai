---
name: rewire
description: "Edit the knowledge graph. Two modes: (1) 'resolve' mode fires when the curation policy flags a contradiction, marking the older fact superseded and linking the new one. (2) 'sweep' mode fires on heartbeat, looking for new entity co-occurrences in recent episodes and adding graph edges."
---

# Rewire policy

## Purpose
Brains don't just store — they *connect*. And when new information contradicts old, brains don't delete the old; they layer the new on top. Rewire implements both.

## Mode: resolve (contradiction handling)

Fires when curation flags `contradiction=true`.

Steps:
1. Look up `old_memory_id` and `new_memory_id` in Kuzu / MemOS.
2. Add `status=superseded` and `superseded_at=now` to the old memory.
3. Create a graph edge `(new_memory)-[:SUPERSEDES]->(old_memory)` with a reason string derived from the contradicting claim.
4. Retain both. Provenance matters. Default retrieval hides superseded memories; `why X` queries walk through them.
5. Log the resolution.

Example:
- Old: "User prefers coffee black" (mem_2201)
- New: "User prefers coffee with oat milk as of April 2026" (mem_9987)
- Edge added: `(mem_9987)-[:SUPERSEDES {reason: "preference_change"}]->(mem_2201)`
- mem_2201 status → superseded. Still retrievable by ID, not by default search.

## Mode: sweep (co-occurrence edge creation)

Fires hourly. Looks at episodes from the last N hours.

Steps:
1. For each recent episode, extract entities (if not already extracted by curation).
2. For each pair of entities that co-occur in the same episode:
   - If the pair has no edge in Kuzu → create `(A)-[:CO_OCCURS_IN {source: episode_id, weight: 1}]->(B)`.
   - If the pair has an existing edge → increment weight, append source.
3. Edges with weight below a threshold older than K days are candidates for pruning (handed off to the pruning policy).

## Cypher patterns

```cypher
// Supersession
MATCH (old:Memory {id: $old_id})
SET old.status = 'superseded', old.superseded_at = datetime()
WITH old
MATCH (new:Memory {id: $new_id})
CREATE (new)-[:SUPERSEDES {reason: $reason, ts: datetime()}]->(old);

// Co-occurrence edge (idempotent)
MERGE (a:Entity {name: $a_name})
MERGE (b:Entity {name: $b_name})
MERGE (a)-[r:CO_OCCURS_IN]->(b)
ON CREATE SET r.weight = 1, r.sources = [$episode_id]
ON MATCH  SET r.weight = r.weight + 1, r.sources = r.sources + $episode_id;
```

## Why this matters

Without rewire, Mini.ai would be a pile of disconnected memories. With rewire:
- The agent can answer "why do you think X?" by walking supersession chains.
- Semantic retrieval gets better over time because entity links create retrieval paths.
- Contradictions become first-class knowledge, not silent inconsistencies.

## Log entries

```json
{"policy":"rewire","mode":"resolve","ts":"...","old":"mem_2201","new":"mem_9987","reason":"preference_change"}
{"policy":"rewire","mode":"sweep","ts":"...","window_h":1,"edges_added":14,"pairs_seen":37}
```
