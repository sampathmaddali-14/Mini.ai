---
name: consolidation
description: "Daily job that summarizes the previous day's episodic memories into semantic memory. This is Mini.ai's sleep analog — the process by which raw experience becomes distilled knowledge. Runs at 03:00 local time."
triggers:
  - cron: "0 3 * * *"
inputs:
  - date: yesterday (ISO)
outputs:
  - semantic_memories_written: int
  - episodes_consolidated: int
  - promoted_to_long_term: int
  - log_entry: json
---

# Consolidation policy

## Purpose
Brains consolidate during sleep: experiences from the day are reviewed, compressed, and moved from hippocampus-dependent (episodic) to neocortex-dependent (semantic) representations. Mini.ai does this nightly.

Without consolidation, the agent drowns in raw episodes and can't see the forest for the trees.

## Steps

### 1. Pull yesterday's episodes
Query MemOS for all episodic memories with timestamp in yesterday's window. Exclude anything tagged `source=reflection` (already summarized).

If the day had fewer than 3 episodes, skip consolidation for that day.

### 2. Cluster by topic
Use embedding-based clustering (HDBSCAN or similar on the episode vectors). Each cluster becomes a candidate for one semantic memory.

Clusters smaller than 2 episodes are not consolidated as clusters — single-episode facts stay episodic until they recur.

### 3. Summarize each cluster
For each cluster, prompt the reasoning model:

> Here are N related episodes from <date>. Produce one or two durable semantic claims that capture what matters from these episodes for future reference. Omit transient details. Each claim must be independently useful without context. If nothing durable is present, return an empty list.

For each claim returned:
- Assign `confidence = f(cluster_size, internal_agreement, user_marker_present)`.
- Write to semantic tier via **curation policy**.
- Tag source episodes with `consolidated=true` and `consolidated_into=<new_semantic_id>`.

### 4. Promote to long-term tier
Scan all semantic memories. Any memory that:
- Has confidence > 0.8, AND
- Is older than 14 days, AND
- Has been accessed at least twice
→ promote by setting `tier=long_term`, `decay_exempt=true`.

Long-term memories are always retrievable; they bypass the decay function.

### 5. Demote stale ones (rare)
Long-term memories that haven't been accessed in 90+ days AND have no incoming graph edges get demoted back to standard semantic. Prevents the long-term tier from calcifying.

### 6. Log summary
Record counts for dashboards and the weekly pruning policy (which uses these counts to tune decay aggressiveness).

## Design notes

- **Use the frontier model here.** Consolidation is the single most important cognitive job and runs only once a day. Spending frontier-model tokens here pays off.
- **Idempotency.** If consolidation fails partway, rerunning on the same date must not create duplicate semantic memories. Check for existing `consolidated_into` tags before writing.
- **Respect curation.** Consolidated memories aren't special — they go through curation's dedup path. Curation will merge near-duplicates (e.g., if a preference was consolidated yesterday and reinforced today).

## Why this is the most important policy

Consolidation is where raw experience becomes knowledge. Every capability that depends on "the agent knows me" depends on consolidation running correctly. If this breaks, Mini.ai regresses to a chat-with-memory — competent, but not actually learning.

## Log entry

```json
{"policy":"consolidation","ts":"2026-04-25T03:02:11Z","date":"2026-04-24","episodes":137,"clusters":18,"semantics_written":14,"promoted":2,"demoted":0,"duration_s":54}
```
