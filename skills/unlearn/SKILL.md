---
name: unlearn
description: "On-demand deletion. Triggered by the user ('forget X') or by a policy ('this was a test, remove the fixtures'). Cascades through graph, writes tombstones, supports recovery within a grace window."
---

# Unlearn policy

## Purpose
The user must be able to tell Mini.ai to forget something, and have it actually be forgotten — from memory, from the graph, from retrieval. With recovery within a grace window in case the forget was wrong.

This is distinct from pruning (automatic, decay-based, weekly) and from rewire's supersession (which retains old facts). Unlearn removes.

## Scope types

| Type | Example | Match strategy |
|---|---|---|
| `topic` | "forget our conversation about the Acme project" | Semantic similarity > 0.75 to a query embedding |
| `entity` | "forget everything about Bob Smith" | Graph traversal — all memories linking to the entity node |
| `time_range` | "forget everything from last Tuesday" | Timestamp filter |
| `memory_id` | "forget mem_8821" | Direct ID |

## Flow

### 1. Resolve scope to memory IDs
Match the scope against MemOS + Kuzu. Produce a list of candidate memory IDs and affected graph nodes.

### 2. Confirmation gate
If estimated deletions > 10: require an explicit confirmation in the user's next turn ("yes, delete 47 memories about Bob Smith"). Show a preview of 3-5 sample titles/snippets.

If estimated deletions ≤ 10: proceed but still log.

### 3. Cascade
For each memory to delete:
- Remove graph edges where it is source or target.
- Note orphaned entity nodes (handled separately — entity nodes are deleted only if no other memories reference them).
- Write a tombstone with recovery blob (full content compressed).
- Delete from Qdrant.

### 4. Entity cleanup
If the scope was an entity and no other memories reference that entity node, delete the entity node too.

### 5. Audit log + user confirmation
Emit a structured log entry. Respond to the user with what was deleted: "Deleted 47 memories and 12 graph edges about Bob Smith. Recoverable until 2026-05-01."

## Recovery

Within 7 days:
```
undelete <memory_id>        # restores single memory + its edges
undelete --scope <original> # restores everything deleted in that scope
```

After 7 days: tombstones are compacted to just {id, deletion_reason, timestamp}. Content is gone.

## Safety gates

- **No silent deletion.** Every unlearn leaves a log and tombstone.
- **No wildcard.** There is no "forget everything" command. If the user wants a full reset, it's an explicit destructive-action confirmation sequence.
- **No deletion of long-term memories without explicit ID match.** Topic or time-range scopes do not match against the long-term tier.
- **Concurrent-safety.** Unlearn takes a write lock per memory. If pruning is running, unlearn waits.

## Log entry

```json
{"policy":"unlearn","ts":"...","trigger":"user","scope":{"type":"entity","value":"Bob Smith"},"matched":47,"deleted":47,"edges":12,"tombstones":47,"confirmed_by_user":true}
```

## What this policy does NOT do (yet)

- **Parametric unlearning.** Removing knowledge from model weights is research-grade and out of scope for v0.1. If the user asks to forget something, and that something is already baked into the reasoning model's training data, Mini.ai cannot scrub it. The memory layer is the only thing we control.
- This is documented clearly to the user so they don't expect more than we deliver.
