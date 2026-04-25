---
name: pruning
description: "Weekly job that deletes memories below the decay threshold. Cascades deletions through the graph, removes orphans, writes tombstones. Runs Sundays at 03:30 local time."
triggers:
  - cron: "30 3 * * 0"
inputs:
  - decay_half_life_days: 14 (episodic) | 180 (semantic)
  - dry_run: false
outputs:
  - memories_deleted: int
  - edges_removed: int
  - orphans_cleaned: int
  - log_entry: json
---

# Pruning policy

## Purpose
Forgetting is a feature. Without it, the memory store fills with trivia and retrieval quality degrades. Pruning is how Mini.ai stays sharp over months and years.

## Decay function

For each memory:

```
decay_score = 1 - exp(-age_days * ln(2) / half_life_days) * (1 + access_bonus)

access_bonus = min(0.5, 0.05 * access_count_last_30d)
```

- `half_life_days` = 14 for episodic, 180 for semantic.
- Long-term tier memories (from consolidation): **exempt** — decay_score=0.
- User-marked "remember this" memories: half-life doubled.
- Memories with >N incoming graph edges: half-life doubled (connected knowledge is stickier).

Threshold for deletion: `decay_score > 0.85`.

## Steps

### 1. Compute decay for all memories
Iterate MemOS memories in batches. Update `decay_score` and `last_decay_computed` fields.

### 2. Select candidates
`decay_score > 0.85 AND tier != long_term AND decay_exempt != true`.

### 3. Cascade cleanup
For each candidate memory:
- Remove graph edges where this memory is source or target.
- If the deletion orphans a graph node (degree=0), queue the node for orphan cleanup.
- Write a **tombstone**: `{id, deleted_at, reason: "decay", supersedes_id?: ...}`. Tombstones are cheap and enable recovery + audit.
- Actually delete the memory content from Qdrant.

### 4. Orphan cleanup
Delete graph nodes with zero edges that are older than 7 days.

### 5. Audit log
Write a deletion log entry per batch:
```json
{"policy":"pruning","ts":"...","deleted":412,"edges_removed":589,"orphans":23,"dry_run":false}
```

### 6. Recovery window
Tombstones are retained for 7 days before being purged themselves. Within that window, `undelete <id>` can restore the memory from the tombstone's recovery blob. After 7 days, tombstones become permanent — only the ID and deletion reason survive.

## Safety gates

- **Dry run first.** The first time a new install runs pruning, force `dry_run=true` and require explicit user confirmation before the next run deletes.
- **Rate limit.** No single pruning pass deletes more than 10% of total memory. If the decay function says more should go, that's a signal the half-life is too aggressive — flag for tuning, don't thrash.
- **Long-term exemption.** The long-term tier must never be pruned by this policy. Removing long-term requires the explicit `unlearn` policy path.

## Log entry

```json
{"policy":"pruning","ts":"2026-04-27T03:31:04Z","deleted":412,"edges_removed":589,"orphans":23,"tombstones_written":412,"dry_run":false,"duration_s":38}
```
