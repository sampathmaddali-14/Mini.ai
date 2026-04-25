---
name: curation
description: "Evaluate a candidate memory before writing to MemOS. Score salience, detect near-duplicates, flag contradictions. Invoke post-turn or whenever a new piece of information is a candidate for persistence. Default policy for every write."
---

# Curation policy

## Purpose
Every memory that enters Mini.ai's long-term store passes through this policy. It is the first line of defense against noise accumulation.

## Decision tree

1. **Explicit user marker?** If the candidate carries `user_override=true` (the user said "remember this"), skip scoring: accept with salience=1.0. Still run dedup.

2. **Compute salience score.** Factors:
   - **Recency** (0-1): fresher = higher. Linear over 24h, floor at 0.1.
   - **Entity density** (0-1): count of named entities / tokens. More entities = more retrievable later.
   - **Repetition signal** (0-1): has this topic been mentioned N times in the last 7 days? Boost if yes.
   - **User-preference match** (0-1): does content match known user preferences (retrieved from semantic memory)?
   - **Emotional/decisional markers** (0-1): presence of "I want", "I decided", "I prefer", "I hate", etc.

   Weighted sum with defaults: recency 0.15, entity 0.25, repetition 0.20, preference 0.20, markers 0.20.

3. **Threshold gate.** If `salience_score < SALIENCE_THRESHOLD` (default 0.3) → **reject**. Log reason.

4. **Near-duplicate check.** Embed candidate, query MemOS for cosine similarity > 0.92 against recent episodic. If hit:
   - Merge: update the existing memory's `occurrence_count`, refresh `last_seen`, boost its salience.
   - Return decision=merge with merge_target_id.

5. **Contradiction check.** For claim-like candidates (contains factual assertions), prompt the reasoning model with the candidate plus top-k retrieved memories and ask: "Does this new statement contradict any retrieved memory?"
   - If yes → set contradiction_flag=true. Do **not** reject the write; instead, write and hand off to the rewire policy to resolve. Return decision=supersede.
   - If no → return decision=accept.

## Implementation notes

- Salience scoring lives in `src/policies/salience.py`.
- Use a cheaper model (Haiku / local) for salience and entity extraction; reserve the frontier model for contradiction checks only.
- Batch entity extraction: don't call the LLM per-turn if a recent entity set already covers the candidate's text.
- Always emit a structured log entry, even on accept. The log is the audit trail.

## Example log entries

```json
{"policy":"curation","ts":"2026-04-24T10:15:33Z","decision":"accept","salience":0.72,"reason":"high entity density, preference match"}
{"policy":"curation","ts":"2026-04-24T10:16:01Z","decision":"reject","salience":0.18,"reason":"low recency, low entity density"}
{"policy":"curation","ts":"2026-04-24T10:22:14Z","decision":"merge","salience":0.64,"merge_target":"mem_8871","reason":"cosine 0.94"}
{"policy":"curation","ts":"2026-04-24T10:30:02Z","decision":"supersede","salience":0.80,"reason":"contradicts mem_4421","handoff":"rewire"}
```

## When NOT to fire

- On retrieval. This policy only runs on writes.
- On system-generated summaries (consolidation output). Those bypass curation — they were already curated upstream.
- On tombstones. Tombstones are structural; they don't need salience.
