---
name: reflection
description: "Run a self-review every 30 minutes. Score recent skill invocations, update skill quality metadata, extract patterns from recent episodes, write insights to semantic memory. This is the 'thinking about your own thinking' layer."
triggers:
  - cron: "*/30 * * * *"
inputs:
  - window_minutes: 30
outputs:
  - insights_written: int
  - skills_scored: int
  - skills_deprecated: int
  - log_entry: json
---

# Reflection policy

## Purpose
Reflection is where Mini.ai thinks about what happened recently and what that means. It's the inner monologue — except it runs even when no one is asking.

## Steps

### 1. Score recent skill invocations
Pull the last 30 minutes of skill invocations from the log. For each:
- If the outcome was `success` → +1 to the skill's success counter.
- If `failure` or `user_correction` → +1 to the failure counter.
- Update the skill's quality score using an EWMA (exponentially-weighted moving average), α=0.2:
  ```
  quality_new = α * (success ? 1 : 0) + (1 - α) * quality_old
  ```

### 2. Deprecate consistently-failing skills
For any skill with quality < 0.3 over ≥10 invocations in the last 7 days:
- Set status=deprecated.
- Don't delete — it might be fixed or may inform future skill generation.
- Log the deprecation.

### 3. Extract insights from recent episodes
Sample the last N episodic memories (default 20). Prompt the reasoning model:

> Given these recent episodes, what patterns, preferences, or facts are emerging about the user or their work? Return 0 to 3 concise semantic claims, each with a confidence score. If nothing meaningful is evident, return an empty list.

For each returned insight:
- Run it through the **curation policy** (yes, reflection writes via curation like everything else).
- If accepted, write as a semantic memory with source=reflection.

### 4. Log a summary
One log entry per firing, even if nothing was produced.

## Design notes

- Reflection writes go through curation. This is important: reflection is a memory producer, not a special case. Same salience rules apply.
- Reflection is cheap — it runs every 30 min. Use a small model for the insight extraction step. Reserve frontier for consolidation (which is daily and deeper).
- If two consecutive reflections produce near-identical insights, curation's dedup will merge them. This is fine.

## Log entries

```json
{"policy":"reflection","ts":"...","window_m":30,"skills_scored":7,"deprecated":0,"insights_candidate":2,"insights_accepted":1}
```

## Anti-patterns to avoid

- Don't let reflection become self-referential — if the log itself becomes a source of "insights", you'll end up with meta-commentary about reflections instead of insights about the user. Filter reflection-source episodes out of the input sample.
- Don't let it run forever on a huge episode window. Hard cap at 30 minutes of data.
