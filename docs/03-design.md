# Mini.ai — Design

## Architectural view

Mini.ai is a layered system with each layer swappable behind a contract. From top to bottom:

```
 ┌──────────────────────────────────────────────────────────┐
 │  L5  Cognitive Policies (the intellectual work)          │
 │      create · curate · refine · rewire · learn · unlearn │
 │      Implemented as SKILL.md files under skills/         │
 └──────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────┐
 │  L4  Skill Runtime (OpenSpace)                           │
 │      Skill loading, execution, evolution, sharing        │
 └──────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────┐
 │  L3  Orchestration (OpenClaw)                            │
 │      Agent loop, heartbeat scheduler, I/O channels       │
 └──────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────┐
 │  L2  Memory OS (MemOS)                                   │
 │      Unified API over three memory tiers                 │
 │      ┌─ Plaintext: episodic & semantic                   │
 │      ├─ Activation: transient working memory             │
 │      └─ Parametric: weights (Phase 2)                    │
 └──────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────┐
 │  L1  Storage Substrate                                   │
 │      Qdrant (vectors)  ·  Kuzu (graph)  ·  SQLite (KV)   │
 └──────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────┐
 │  L0  Reasoning Substrate                                 │
 │      Claude API (default)  ·  local model (optional)     │
 └──────────────────────────────────────────────────────────┘
```

## Data flow: a single turn

1. **Input arrives** on an OpenClaw channel (CLI or messaging).
2. **Pre-turn recall:** OpenClaw plugin queries MemOS with the input → MemOS does hybrid retrieval (Qdrant vector + Kuzu graph) → returns top-k relevant memories.
3. **Context assembly:** System prompt + tool schemas + retrieved memories + skill library index + input → sent to Claude.
4. **Reasoning + action:** Claude decides to invoke skills via tool calls. OpenSpace loads any new skills on demand (progressive disclosure).
5. **Response out** to the user via the same channel.
6. **Post-turn capture:** The turn (input, retrieved context, actions, response) is submitted to the **curation policy** (L5) for salience scoring.
7. **If it passes:** the curation policy writes to MemOS, which routes to Qdrant (vectors) and Kuzu (graph edges) appropriately.
8. **If a contradiction is flagged:** the rewire policy fires, marks the older fact superseded, and links the two.

## Data flow: heartbeat (agent thinks while you're not there)

OpenClaw's heartbeat daemon fires cron-style schedules. Each schedule invokes a policy skill:

- **Every 30 min:** refine pass — score recent skill invocations, update quality metadata.
- **Hourly:** rewire sweep — look for new entity co-occurrences in last hour's episodes, add graph edges.
- **Daily at 03:00:** consolidation — summarize yesterday's episodic memories into semantic memory. This is the "sleep" analog.
- **Weekly at Sunday 03:30:** pruning pass — delete memories below decay threshold, orphan graph nodes.
- **On-demand:** unlearn — user-triggered or policy-triggered deletion with cascade.

## Component contracts

### OpenClaw → MemOS (via plugin)

OpenClaw invokes MemOS before and after each agent turn. The plugin is already published as `@memtensor/memos-local-openclaw-plugin`. No custom code needed for basic wiring.

### MemOS → Qdrant + Kuzu

MemOS is configured with dual backend: Qdrant for vector memory, Kuzu for graph memory. Configuration lives in `infra/memos.config.json`.

### OpenSpace → OpenClaw

OpenSpace runs as an MCP server. OpenClaw discovers it via the standard MCP mechanism. Skills live under `skills/` and are loaded lazily. OpenSpace handles skill evolution automatically based on invocation outcomes.

### Cognitive Policies → Everything else

Each policy is a SKILL.md file plus a small Python module in `src/policies/`. The SKILL.md is what the agent reads when deciding to invoke the policy. The Python module is what actually runs. This split matches the OpenSpace pattern.

## Memory model

Three tiers, all addressable through MemOS's unified API:

**Episodic** — raw events with timestamps. High write rate, high decay rate. Stored primarily in Qdrant with graph links in Kuzu. Example: "User asked about Docker networking at 2026-04-24T10:15Z, received answer X."

**Semantic** — distilled facts, low write rate, low decay rate. Produced by the consolidation policy from episodic memories. Example: "User prefers Docker Compose over Kubernetes for personal projects."

**Procedural** — skills. Executable code with embeddings of their descriptions. Stored in OpenSpace's skill library. Example: a `deploy_to_vps` skill generated after deploying three times.

## Cognitive policy contracts

Each policy has a standard interface:

```python
def run(context: PolicyContext) -> PolicyResult:
    """
    Inputs: read access to MemOS, Kuzu, OpenSpace skill library
    Outputs: writes/edits/deletions + a structured log entry
    """
```

The six policies, their triggers, and their primary effects:

| Policy | Trigger | Primary effect |
|---|---|---|
| curation | Post-turn | Accept/reject/merge candidate memory |
| rewire | Contradiction flag | Edit graph — supersede + link |
| reflection | Heartbeat (30 min) | Update skill quality; generate insights |
| consolidation | Heartbeat (daily) | Episodic → semantic summarization |
| pruning | Heartbeat (weekly) | Delete low-value memories + orphan edges |
| unlearn | User request or policy | Cascade delete with tombstones |

## Deployment topology

```
┌─ Single VM or container host ─────────────────────────────┐
│                                                           │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐              │
│  │ OpenClaw │   │ OpenSpace│   │  MemOS   │              │
│  │  daemon  │   │   (MCP)  │   │   API    │              │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘              │
│       └──────────────┴──────────────┘                     │
│                      │                                    │
│       ┌──────────────┼──────────────┐                     │
│       ▼              ▼              ▼                     │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                │
│  │ Qdrant  │    │  Kuzu   │    │ SQLite  │                │
│  │ (vec)   │    │ (graph) │    │ (kv/log)│                │
│  └─────────┘    └─────────┘    └─────────┘                │
│                                                           │
│  Volume mounts: ./data/{qdrant,kuzu,memos,skills}         │
└───────────────────────────────────────────────────────────┘
        │
        ▼  HTTPS
   Claude API (external)
```

All intra-container traffic on a Docker bridge network. Only outbound egress is to the Claude API. Storage is volume-mounted for persistence across container restarts.

## Configuration surface

Environment-driven, loaded from `.env`:

- `ANTHROPIC_API_KEY` — reasoning substrate
- `MEMOS_CONFIG_PATH` — where MemOS loads its config
- `QDRANT_URL`, `KUZU_PATH` — storage connections
- `HEARTBEAT_ENABLED` — master switch for background jobs
- `SALIENCE_THRESHOLD` — numeric, tunable (default 0.3)
- `DECAY_HALF_LIFE_DAYS` — pruning aggressiveness (default 14)
- `LOG_LEVEL` — structured logging

## Security posture (v0.1)

- No authentication — single-user local deployment assumed.
- API keys stored only in `.env`, never committed.
- All data local to the host. Nothing sent to a cloud memory service.
- Outbound calls only to the configured LLM endpoint.
- Phase 2 adds: TLS on all services, per-skill execution sandboxing, audit log signing.

## Open questions deferred to Phase 2

1. Multi-user support and memory-cube isolation.
2. Parametric unlearning (weight-level, research problem).
3. Multimodal memory (images, audio, tool traces as first-class).
4. Hyperscaler-specific deployment (current Docker Compose is substrate-agnostic).
5. Federated skill sharing across instances.
