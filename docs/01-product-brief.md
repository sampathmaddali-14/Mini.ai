# Mini.ai — Product Brief

## Vision

A personal agentic system that behaves less like a chatbot and more like a second mind — one that accumulates experience, forms opinions, revises them when wrong, and quietly improves without supervision. The goal is not neural mimicry but **functional mimicry of how brains handle knowledge over time**: through consolidation, decay, contradiction resolution, and skill formation.

## Problem

Current LLM agents are stateless by default. Even when wired with memory layers, they:

- Accumulate indefinitely without forgetting, becoming noisy over time.
- Cannot resolve contradictions — new information sits alongside outdated information.
- Learn at the conversation scale but not across days, weeks, months.
- Treat every session as independent, so skills never compound.
- Lack the "sleep" phase that lets brains consolidate and prune.

The result is agents that feel smart in demos and mediocre after a month.

## Solution

Mini.ai is an assembly of six permissively-licensed open-source components, plus six cognitive policies that wire them into a brain-mimicking loop.

The six verbs (create, curate, refine, rewire, learn, unlearn) are not features — they are the primitives. Every other behavior is a composition of these.

## Target user

Initially: a single technical user (the author) who wants a personal assistant that gets better with use. Phase 2: small teams sharing a collective memory cube. Not a general consumer product.

## Guiding principles

1. **Permissive licensing only.** No GPL, AGPL, or open-core traps. Anything included must be deployable on any hyperscaler with no legal review.
2. **Memory is first-class.** It is not a RAG bolt-on. It is the substrate. Reasoning happens around and through it.
3. **Forgetting is a feature.** Aggressive pruning, decay, and supersession are non-negotiable. The system's usefulness depends on what it stops remembering.
4. **Skills compound.** Every solved problem becomes a reusable skill. The agent's capability grows as a function of use, not version releases.
5. **Autonomy over supervision.** The agent should do useful work on its own schedule (heartbeat), not wait for prompts.
6. **Small and composable.** No monoliths. Each component swappable. No framework lock-in.

## Non-goals

- Training a new foundation model. Reasoning is delegated to hosted LLMs initially.
- Literal neural / spiking simulation. The brain analogy is functional, not anatomical.
- Multi-tenant SaaS. This is single-user until proven otherwise.
- Replacing Claude, GPT, or any frontier model. Mini.ai uses them.

## Success criteria

After 30 days of daily use, the system must demonstrably:

1. Recall user preferences established in week one, unprompted.
2. Have at least three automatically-generated skills in its skill library.
3. Show evidence of consolidation — episodic memories from week one have been summarized into semantic facts.
4. Show evidence of pruning — low-value memories from week one no longer surface in retrieval.
5. Correctly handle at least one contradiction (new information overrides old).
6. Operate for 24+ hours without human intervention (heartbeat-driven tasks succeed).

If any of these fail, the cognitive policies need work — not the stack.

## Scope boundaries

**In scope for v0.1:** single-user local deployment, all six cognitive policies, local heartbeat, basic skill evolution, contradiction detection.

**Out of scope for v0.1:** multi-user access control, parametric unlearning (weight-level), multimodal memory, voice I/O, cloud-hosted deployment, observability dashboards.

**Out of scope permanently:** anything requiring copyleft licenses, closed-source dependencies, or vendor lock-in.
