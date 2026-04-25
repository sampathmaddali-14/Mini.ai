# Mini.ai — Design

> **v0.1 reality check (2026-04-25):** The original design assumed MemOS, OpenClaw, and OpenSpace each ran as separate Docker containers connected by HTTP. In practice the upstream projects ship differently — OpenClaw and OpenSpace install on the host; MemOS runs as an in-process plugin inside OpenClaw with built-in SQLite/FTS5/vector storage. This document has been updated to reflect that. The original four-tier "Plaintext / Activation / Parametric" memory model and the six cognitive policies remain unchanged. The deployment topology and the L1/L2 wiring are the parts that moved. See [`04-deployment-reality.md`](04-deployment-reality.md) for the rationale.

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
 │      Runs on host as an MCP server (openspace-mcp)       │
 └──────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────┐
 │  L3  Orchestration (OpenClaw)                            │
 │      Agent loop, gateway, plugin host, I/O channels      │
 │      Runs on host (Node 24, npm-installed)               │
 └──────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────┐
 │  L2  Memory OS (MemOS Local OpenClaw plugin)             │
 │      Recall before turn / capture after turn             │
 │      In-process inside OpenClaw — not a separate service │
 │      ┌─ Plaintext: episodic & semantic (SQLite)          │
 │      ├─ Activation: working set (in-memory)              │
 │      └─ Parametric: weights (Phase 2)                    │
 └──────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────┐
 │  L1  Storage Substrate                                   │
 │      v0.1: SQLite (KV + FTS5 + vector, in plugin)        │
 │      Phase 1b/2 (optional): Qdrant (vectors), Kuzu (graph)│
 └──────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────┐
 │  L0  Reasoning Substrate                                 │
 │      Claude API (default)  ·  local model (optional)     │
 └──────────────────────────────────────────────────────────┘
```

## Data flow: a single turn

1. **Input arrives** on an OpenClaw channel (CLI or messaging).
2. **Pre-turn recall:** the MemOS Local plugin's `before_agent_start` hook fires — runs hybrid SQLite FTS5 + vector retrieval and injects top-k relevant memories into the prompt.
3. **Context assembly:** System prompt + tool schemas + retrieved memories + skill library index + input → sent to Claude.
4. **Reasoning + action:** Claude decides to invoke skills via tool calls. OpenSpace (over MCP) loads any new skills on demand (progressive disclosure).
5. **Response out** to the user via the same channel.
6. **Post-turn capture:** The plugin's `agent_end` hook fires. The captured turn is then submitted to the **curation policy** (L5) for salience scoring before final persistence (curation logic is Mini.ai's, not the plugin's default behavior — wiring this is a Sprint 0 task).
7. **If it passes:** the curation policy persists to the plugin's local store (SQLite + vector index).
8. **If a contradiction is flagged:** the rewire policy fires, marks the older fact superseded, and links the two.

## Data flow: heartbeat (agent thinks while you're not there)

A scheduler fires cron-style policies on a recurring cadence. **Open question for Sprint 0**: whether OpenClaw's gateway provides a built-in cron facility we can hook into, or whether we run a small standalone Python scheduler (`apscheduler`) under `src/core/heartbeat.py` that invokes OpenSpace skills via MCP. Either way the schedule is:

- **Every 30 min:** refine pass — score recent skill invocations, update quality metadata.
- **Hourly:** rewire sweep — look for new entity co-occurrences in last hour's episodes, update local graph state in the plugin store.
- **Daily at 03:00:** consolidation — summarize yesterday's episodic memories into semantic memory. This is the "sleep" analog.
- **Weekly at Sunday 03:30:** pruning pass — delete memories below decay threshold.
- **On-demand:** unlearn — user-triggered or policy-triggered deletion with cascade.

## Component contracts

### OpenClaw ↔ MemOS Local plugin

The plugin runs in-process inside OpenClaw's gateway. It exposes two lifecycle hooks: `before_agent_start` (recall) and `agent_end` (capture). It owns its own SQLite database for plaintext memory, FTS5 for keyword search, and a vector index. **Mini.ai does not own any code here** — the plugin is upstream maintained.

The Mini.ai-specific curation, rewire, etc. policies operate on top of the plugin's store, either by:
- (a) Running as OpenSpace skills the agent itself decides to invoke at the right moments, or
- (b) Listening for plugin-emitted events and reacting (if/when the plugin grows that surface).

Sprint 0 starts with (a) since it's the path the upstream plugin already supports. Plugin config lives in `~/.openclaw/openclaw.json` under `plugins.entries.memos-local-openclaw-plugin.config`.

### OpenSpace ↔ OpenClaw

OpenSpace runs as an MCP server (`openspace-mcp`). OpenClaw discovers it via standard MCP config in `~/.openclaw/openclaw.json` under `mcpServers.openspace`. OpenSpace exposes four tools: `execute_task`, `search_skills`, `fix_skill`, `upload_skill`. Skills live under Mini.ai's `skills/` directory, pointed at by `OPENSPACE_HOST_SKILL_DIRS`. OpenSpace handles skill evolution automatically based on invocation outcomes.

### Cognitive Policies ↔ OpenSpace

Each policy is a SKILL.md file under `skills/<verb>/`. The SKILL.md is what the agent reads when deciding to invoke the policy. The Python module under `src/policies/<verb>.py` holds the pure logic (salience scoring, decay function, threshold rules) and is callable from a small wrapper invoked by OpenSpace. Sprint 0 includes the work of finalizing exactly how `src/policies/*.py` is invoked from a SKILL.md (script subprocess vs imported module).

## Memory model

Three tiers, all addressable through MemOS's unified API:

**Episodic** — raw events with timestamps. High write rate, high decay rate. Stored in the MemOS Local plugin's SQLite + vector index. Example: "User asked about Docker networking at 2026-04-24T10:15Z, received answer X."

**Semantic** — distilled facts, low write rate, low decay rate. Produced by the consolidation policy from episodic memories. Same physical store as episodic, distinguished by tier metadata.

**Procedural** — skills. Markdown specs (SKILL.md) plus optional supporting code under `skills/`. Loaded by OpenSpace and exposed to OpenClaw via MCP. Example: a `deploy_to_vps` skill generated after deploying three times.

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
┌─ Host machine (your laptop / VM) ─────────────────────────┐
│                                                           │
│   ┌────────────────────────────────────────────┐          │
│   │  OpenClaw (Node 24, npm-installed)         │          │
│   │   ├─ gateway + channels (CLI, etc.)        │          │
│   │   └─ MemOS Local plugin (in-process)       │          │
│   │        └─ SQLite + FTS5 + vector  ─────────┐│         │
│   └─────────────────┬──────────────────────────┘          │
│                     │ MCP (stdio or HTTP)                 │
│                     ▼                                     │
│   ┌────────────────────────────────────────────┐          │
│   │  OpenSpace (Python 3.12, openspace-mcp)    │          │
│   │   ├─ skill loader (reads Mini.ai/skills/)  │          │
│   │   ├─ skill evolution                       │          │
│   │   └─ tools: execute_task, search_skills,   │          │
│   │            fix_skill, upload_skill          │          │
│   └────────────────────────────────────────────┘          │
│                                                           │
│   Mini.ai files (this repo)                               │
│   ├─ skills/<verb>/SKILL.md      ← exposed by OpenSpace   │
│   ├─ src/policies/<verb>.py      ← pure logic             │
│   └─ src/core/heartbeat.py (TBD) ← schedule for policies  │
│                                                           │
│   Optional (Phase 1b):                                    │
│   docker compose up qdrant kuzu                           │
└───────────────────────────────────────────────────────────┘
        │
        ▼  HTTPS
   Claude API (external)
```

Everything in v0.1 runs on the host. Only outbound egress is to the Claude API (and optionally MemOS Cloud or OpenSpace's cloud skill registry, both opt-in). The MemOS Local plugin's SQLite file is the persistence layer.

## Configuration surface

Three places hold config:

1. **`~/.openclaw/openclaw.json`** — OpenClaw gateway, channels, plugins, MCP servers (incl. OpenSpace). Owned by OpenClaw / MemOS plugin. Mini.ai contributes the OpenSpace MCP entry pointing at `Mini.ai/skills/`.
2. **`~/.openclaw/.env`** — credentials read by the MemOS Local plugin (sandboxed, does not see process env).
3. **`Mini.ai/.env`** — Mini.ai's own Python policy modules and tests.

Mini.ai-owned env vars (in `Mini.ai/.env`):

- `ANTHROPIC_API_KEY` — reasoning substrate (also used by OpenSpace via auto-detection)
- `HEARTBEAT_ENABLED` — master switch for background scheduler (when implemented)
- `SALIENCE_THRESHOLD` — numeric, tunable (default 0.3)
- `DECAY_HALF_LIFE_DAYS` — pruning aggressiveness (default 14)
- `LOG_LEVEL` — structured logging

OpenSpace-owned env vars (set in `~/.openclaw/openclaw.json` under `mcpServers.openspace.env`):

- `OPENSPACE_HOST_SKILL_DIRS` — absolute path to `Mini.ai/skills/`
- `OPENSPACE_WORKSPACE` — absolute path to the OpenSpace clone
- `OPENSPACE_API_KEY` — optional, for the cloud skill community

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
4. Hyperscaler-specific deployment — `infra/gcp/` is currently broken vs. the host-install path; needs a redesign.
5. Federated skill sharing across instances (OpenSpace's cloud community is the closest fit).
6. Whether to migrate L1 storage from the plugin's bundled SQLite to dedicated Qdrant + Kuzu containers if the rewire/graph workload outgrows SQLite.
