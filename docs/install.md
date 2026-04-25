# Mini.ai — Install (local-first)

This is the v0.1 install guide for **Architecture L** (local-first, host install). For the rationale behind this shape, see [`04-deployment-reality.md`](04-deployment-reality.md).

> **TL;DR:** OpenClaw, OpenSpace, and the MemOS Local plugin all install on your host machine. No Docker required. SQLite + FTS5 + vector search ships with the MemOS Local plugin — no separate vector or graph store needed for v0.1.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Node.js | 24 (or 22.14+) | For OpenClaw + MemOS plugin |
| Python | 3.12+ | For OpenSpace + Mini.ai policy logic |
| Anthropic API key | — | Get one at https://console.anthropic.com/settings/keys |

On macOS:

```bash
brew install node@24 python@3.12
node --version    # v24.x
python3.12 --version
```

---

## 1. Install OpenClaw

OpenClaw is the agent runtime — message channels, plugin host, and gateway. We use the recommended onboarding flow.

```bash
# In your home directory
npx openclaw onboard
```

This walks you through gateway setup, picking channels (start with **CLI** for v0.1), and basic config. Config lands in `~/.openclaw/openclaw.json`.

Verify:

```bash
openclaw --version
openclaw gateway start    # in one terminal — leave running
```

In a second terminal you should be able to send a message via the CLI channel and get a response.

> **Detailed OpenClaw docs:** https://docs.openclaw.ai/start/getting-started

---

## 2. Install the MemOS Local OpenClaw plugin

This gives OpenClaw long-term memory backed by on-device SQLite + FTS5 + vector search. No external vector or graph store needed.

```bash
openclaw plugins install @memtensor/memos-local-openclaw-plugin@latest
openclaw gateway restart
```

Confirm the plugin is enabled in `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "memos-local-openclaw-plugin": { "enabled": true }
    }
  }
}
```

After restart, the plugin runs `before_agent_start` (recall) and `agent_end` (capture) hooks for every turn, transparently.

> **Plugin homepage:** https://memos-claw.openmem.net
> **NPM:** https://www.npmjs.com/package/@memtensor/memos-local-openclaw-plugin

---

## 3. Install OpenSpace

OpenSpace is the skill runtime — it handles skill loading, evolution, and exposes our `skills/` directory to OpenClaw via MCP.

```bash
git clone --filter=blob:none --sparse https://github.com/HKUDS/OpenSpace.git
cd OpenSpace
git sparse-checkout set '/*' '!assets/'   # skip the ~50MB assets folder
pip install -e .
openspace-mcp --help                       # verify install
cd ..
```

### Wire OpenSpace into OpenClaw

Add OpenSpace as an MCP server in OpenClaw's config. Edit `~/.openclaw/openclaw.json` and add:

```json
{
  "mcpServers": {
    "openspace": {
      "command": "openspace-mcp",
      "toolTimeout": 600,
      "env": {
        "OPENSPACE_HOST_SKILL_DIRS": "/absolute/path/to/Mini.ai/skills",
        "OPENSPACE_WORKSPACE": "/absolute/path/to/OpenSpace"
      }
    }
  }
}
```

Replace the two `/absolute/path/to/...` paths with your actual paths. Then `openclaw gateway restart`.

### Copy OpenSpace's "host skills" into Mini.ai's skill dir

These two skills teach the agent when and how to call OpenSpace itself:

```bash
cp -r OpenSpace/openspace/host_skills/delegate-task/   /path/to/Mini.ai/skills/
cp -r OpenSpace/openspace/host_skills/skill-discovery/ /path/to/Mini.ai/skills/
```

> **OpenSpace docs:** https://github.com/HKUDS/OpenSpace
> **Per-agent (OpenClaw) integration notes:** `OpenSpace/openspace/host_skills/README.md`

---

## 4. Verify the loop end-to-end

1. **Gateway up:** `openclaw gateway start` (terminal A)
2. **CLI in:** Open a channel and send a message — confirm a response.
3. **Memory captured:** Send `remember this: I prefer Docker Compose over Kubernetes`.
4. **Memory recalled:** In a fresh turn, ask: `what do I prefer for orchestration?` — the local plugin should surface the prior memory.
5. **OpenSpace reachable:** Ask: `list available skills` — OpenClaw should call OpenSpace's `search_skills` and list the skills under `Mini.ai/skills/`.

If all four work, the v0.1 loop is alive. Tick **S001 + S002 + S009 + S012 + S013** in `TODO.md`.

---

## What about Qdrant and Kuzu?

The original design called for Qdrant (vector) and Kuzu (graph) as separate services. The MemOS Local plugin ships its own SQLite + FTS5 + vector pipeline, so they're **not required for v0.1**.

`infra/docker-compose.yml` keeps Qdrant and Kuzu available as **optional, future-use** services for Phase 1b experiments (e.g., a richer graph for the rewire policy than SQLite can provide). They're not part of the running stack right now.

---

## Troubleshooting

**`openclaw onboard` fails on Windows.** Use WSL2. Native Windows is not the recommended path.

**Plugin install fails with `spawn EINVAL` on Windows.** Manual install via NPM tgz — see https://github.com/MemTensor/MemOS-Cloud-OpenClaw-Plugin#option-b--manual-install-workaround-for-windows (the local-plugin uses the same workaround).

**OpenSpace `pip install -e .` fails on Python 3.13+.** OpenSpace targets 3.12. Use `python3.12` explicitly.

**MCP server doesn't show up in OpenClaw.** Confirm `command: "openspace-mcp"` is on `PATH` (test in shell: `which openspace-mcp`). If you used a venv for OpenSpace, point `command` at the venv's binary.

**`ANTHROPIC_API_KEY` not picked up.** Both OpenClaw and OpenSpace read from the host's env or their respective `.env` files. The MemOS Local plugin reads from `~/.openclaw/.env`.

---

## What's *not* in this v0.1 install

- No Telegram, Slack, or other channels — only CLI. Add channels via OpenClaw's plugin/onboarding once CLI is solid.
- No GCP / cloud deploy. `infra/gcp/` is deferred to Phase 2 and currently does not match this install path.
- No heartbeat scheduler yet — needs verification that OpenClaw's gateway has a built-in cron, otherwise we add a tiny Python daemon.
- No Mini.ai Python policy modules wired in yet — the logic in `src/policies/*.py` will be reshaped into proper OpenSpace skills as Sprint 0 progresses.
