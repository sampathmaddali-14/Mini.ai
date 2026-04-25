# Mini.ai — Deployment Reality Check

Status: **draft, awaiting decision** — written 2026-04-25 after `S001` failed because 3 of 5 Docker images referenced in `infra/docker-compose.yml` do not exist.

## TL;DR

The original compose file was authored on guessed image names. The upstream projects (OpenClaw, MemOS, OpenSpace) are all real and active, but they ship in a different shape than the compose assumed. This doc records what's actually true and proposes a Sprint 0 reset that matches reality.

---

## What each component actually is

### OpenClaw — `github.com/openclaw/openclaw` (363k★, MIT)
- Personal AI assistant — runs **on your devices**, not as a backend service.
- Install: `npx openclaw onboard` (Node 24, or 22.14+). macOS / Linux / Windows-via-WSL2.
- Has a Docker option (`docs.openclaw.ai/install/docker`) but host install is the recommended path.
- Channels: WhatsApp, Telegram, Slack, Discord, iMessage, CLI, ~24 others.
- Plugin architecture: `openclaw plugins install <npm-package>`. Config in `~/.openclaw/openclaw.json`.
- **There is no `openclaw/openclaw:latest` Docker image.**

### MemOS — `github.com/MemTensor/MemOS` (8.7k★, Apache-2.0)
- Memory OS for LLM agents. Distributed as **Python package `MemoryOS`** on PyPI, plus services.
- Two integration plugins for OpenClaw, both NPM-published:
  - `@memtensor/memos-cloud-openclaw-plugin` — talks to MemOS Cloud (SaaS, requires `MEMOS_API_KEY`).
  - `@memtensor/memos-local-openclaw-plugin` — 100% on-device. SQLite + FTS5 + vector search built in.
- The plugin is a **Node lifecycle plugin** that runs *inside* OpenClaw's gateway, not a separate service.
- **There is no `memtensor/memos:latest` Docker image.** A standalone MemOS HTTP service can be built from source if needed, but is not the canonical path for the OpenClaw integration.
- License confirmed Apache-2.0 — fine.

### OpenSpace — `github.com/HKUDS/OpenSpace` (5.7k★, MIT)
- Skill runtime / self-evolving skill library. Python 3.12+.
- Runs as an **MCP server** (stdio, SSE, or streamable HTTP). Plugs into any MCP-aware agent: Claude Code, Codex, OpenClaw, nanobot, Cursor.
- Provides AUTO-FIX / AUTO-IMPROVE / AUTO-LEARN over a skill directory.
- Skills live in a directory you point it at (e.g. our `skills/`).
- **There is no `hkuds/openspace:latest` Docker image.** Install via Python package or source.

### Qdrant — works as-is (Apache-2.0). `qdrant/qdrant:latest` exists.
### Kuzu — works as-is (MIT). `kuzudb/api-server:latest` exists.

---

## What this means for Mini.ai

### The upstream plugin already does what compose was building

The MemOS **Local** plugin includes SQLite + FTS5 + vector search end-to-end inside OpenClaw. That replaces:
- `qdrant` container (vector store)
- `kuzu` container (graph store)
- `memos` container (memory OS)

Three containers collapse to one npm-installed plugin. The Sprint 0 stories S006 / S007 / S008 / S009 / S010 are largely subsumed by `openclaw plugins install @memtensor/memos-local-openclaw-plugin`.

### OpenSpace replaces "skill runtime"

OpenSpace already does the skill-quality EWMA, skill evolution, and MCP server bits that some of our policies were going to implement. Stories S013 / S015 / S027 / S029 / S041–S044 are partly upstream territory.

### Our six Python policies have an impedance mismatch

`src/core/memory_bridge.py` is described in the README as a "thin MemOS HTTP client". The Local plugin runs in-process inside OpenClaw (Node), so there's no HTTP endpoint to call. The six policy implementations in `src/policies/*.py` need to either:

- **Path A — Run as OpenSpace skills.** Rewrite each policy as a skill in our `skills/` directory, exposed to OpenClaw via OpenSpace's MCP. This is the upstream-aligned path. Cost: rewrite (the *logic* in `salience.py`, `pruning.py`, etc. mostly survives — it's the integration glue that changes).
- **Path B — Run a local MemOS HTTP service from source.** Build MemOS as a standalone service so the existing Python code can speak HTTP to it. Preserves `memory_bridge.py` shape. Cost: we maintain a build/deploy of MemOS-as-service that nobody upstream supports.

**Path A is recommended** — less code we own, integrates with the actual upstream story, and keeps the policy *logic* (which is the interesting part) intact.

---

## Two viable architectures

### Architecture L — Local-first (recommended for v0.1)

```
Host machine (your Mac):
  ├─ OpenClaw         (npm: openclaw onboard)
  │    └─ MemOS Local Plugin   (npm: @memtensor/memos-local-openclaw-plugin)
  │         └─ SQLite + FTS5 + vector
  ├─ OpenSpace        (Python: pip install openspace)  → MCP server
  │    └─ skills/  (our cognitive policies as skills)
  └─ Mini.ai code     (Python: src/policies/*.py loaded as OpenSpace skills)

No Docker required for v0.1.
```

Matches the brief's "permissive, single-user, local-first" stance. Lowest moving parts.

### Architecture C — Cloud-memory variant

Same as L, but swap `memos-local-openclaw-plugin` for `memos-cloud-openclaw-plugin`. Requires a MemOS API key. Better multi-agent memory sharing if we ever need it. Adds a paid hosted dependency. Out of scope for v0.1 unless we explicitly want it.

---

## What needs to change in this repo

If you accept the pivot:

1. **`infra/docker-compose.yml`** — keep only `qdrant` and `kuzu` (optional, useful as fallback storage but not required). Remove `memos`, `openspace`, `openclaw` services. Add a comment block explaining the host-install path. Or **delete the file entirely** and replace with a `docs/install.md`. Delete is cleaner.
2. **`docs/03-design.md`** — fix the L1–L4 topology diagram. The "MemOS HTTP service" + "Qdrant container" + "Kuzu container" picture is wrong for the local plugin path.
3. **`docs/03-design.md` line 63** — `@memtensor/memos-local-openclaw-plugin` reference is correct on the package name. The "OpenClaw discovers it via the standard MCP mechanism" claim about OpenSpace ↔ OpenClaw is correct.
4. **`README.md`** — replace the "Getting started — local" Docker Compose snippet with the host-install steps.
5. **`src/core/memory_bridge.py`** — HTTP client to a service that doesn't exist. Either delete (Path A) or repurpose (Path B).
6. **`src/policies/*.py`** — keep the *logic* (salience scoring, decay, curation thresholds, etc.). Replace the integration shell with OpenSpace skill scaffolding.
7. **`skills/<verb>/SKILL.md`** — the spec format may need to align with OpenSpace's actual SKILL.md schema. Verify.
8. **`infra/memos.config.json`** — the local plugin doesn't read this. Delete or repurpose.
9. **`infra/openclaw.config.json`** — needs to match the real OpenClaw config schema (`~/.openclaw/openclaw.json`). Verify.
10. **`infra/gcp/`** — the GCP deploy plan deploys a stack that doesn't work. Either delete (defer to Phase 2) or rewrite to deploy host-install + reverse proxy. Defer is fine for v0.1.
11. **`TODO.md`** Sprint 0 — un-tick the "Phase 0 done" claim where it overstates reality. Reorganize Week 1 around: install Node+Python, `openclaw onboard`, install MemOS local plugin, install OpenSpace, wire skills/.

---

## Risks of the pivot

- **Loss of "Docker-up" simplicity.** Host install means Node/Python version management on the user's machine. Mitigated by clear docs and (later) a Dockerfile that bundles all three.
- **OpenSpace skill format may not perfectly match our SKILL.md format.** We may have to reshape the six skill stubs.
- **Heartbeat scheduling** (S003) — need to check whether OpenClaw provides cron-style scheduling natively, or whether we need a separate scheduler. If separate, a tiny Python `apscheduler` daemon in `src/core/heartbeat.py` is sufficient.

## Risks of *not* pivoting

- **Sprint 0 cannot complete.** The current compose cannot bring up the stack at all. Every story that depends on a running MemOS / OpenClaw / OpenSpace is blocked until we fix this.
- **The Mini.ai promise (long-term memory, skill evolution) is already built upstream.** Rebuilding it ourselves duplicates work and diverges from a community we'd otherwise inherit.

---

## Decision needed

- [ ] Accept Architecture **L** (local-first, host install, MemOS Local plugin) and start the cleanup.
- [ ] Accept Architecture **C** (MemOS Cloud).
- [ ] Reject the pivot — push back, propose alternative.
- [ ] Pause and gather more info on a specific point.

Once a path is chosen, the cleanup can be done as a single PR (compose deletion + design.md fix + README + TODO.md re-plan + small src/ cleanup), reviewed, then merged.
