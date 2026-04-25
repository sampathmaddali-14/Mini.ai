# Mini.ai

A brain-mimicking agentic architecture that can **create, curate, refine, rewire, learn, and unlearn** — approximating the functional patterns of human cognition rather than literal neural mimicry.

## Stack

All components are permissively licensed (MIT / Apache 2.0). Zero copyleft.

For v0.1 the stack runs **on the host** — see [`docs/install.md`](docs/install.md) and [`docs/04-deployment-reality.md`](docs/04-deployment-reality.md) for the rationale.

| Layer | Component | License | How it runs |
|---|---|---|---|
| Orchestration | [OpenClaw](https://github.com/openclaw/openclaw) | MIT | host (Node 24, `openclaw onboard`) |
| Memory OS | [MemOS Local plugin](https://github.com/MemTensor/MemOS) | Apache 2.0 | OpenClaw plugin (`@memtensor/memos-local-openclaw-plugin`) |
| Skill library | [OpenSpace](https://github.com/HKUDS/OpenSpace) | MIT | host MCP server (`openspace-mcp`, Python 3.12) |
| Vector store (optional) | Qdrant | Apache 2.0 | Docker, deferred to Phase 1b |
| Graph store (optional) | Kuzu | MIT | Docker, deferred to Phase 1b |
| Reasoning | Claude API | N/A (hosted) | external |

## Repository layout

```
mini-ai/
├── docs/                            product brief, capabilities, design
│   ├── 01-product-brief.md
│   ├── 02-capabilities.md
│   └── 03-design.md
├── backlog.xlsx                     Epics + Stories + Sprint 0 + Risks
├── skills/                          cognitive policy skill specs (SKILL.md)
│   ├── curation/                    write-path filter
│   ├── rewire/                      graph editing
│   ├── reflection/                  30-min self-review
│   ├── consolidation/               nightly episodic→semantic
│   ├── pruning/                     weekly decay delete
│   └── unlearn/                     on-demand forget
├── src/
│   ├── core/
│   │   ├── memory_bridge.py         thin MemOS HTTP client
│   │   ├── policy_base.py           CognitivePolicy base + PolicyContext + LLMClient
│   │   ├── cognitive_loop.py        operator entrypoint, health, fixture seeding
│   │   ├── run_policy.py            CLI to fire any policy by name
│   │   └── inspect.py               memory inspector CLI
│   └── policies/
│       ├── salience.py              pure scoring function (unit-tested)
│       ├── curation.py              accept/reject/merge/supersede logic
│       ├── rewire.py                Kuzu graph ops (resolve + sweep modes)
│       ├── reflection.py            skill quality EWMA + insight extraction
│       ├── consolidation.py         nightly summarization (clusters → claims)
│       ├── pruning.py               decay function + cascade delete + tombstones
│       └── unlearn.py               scoped deletion with recovery
├── tests/
│   └── test_pure_logic.py           10 passing tests: salience + decay
├── infra/
│   ├── docker-compose.yml           local stack
│   ├── memos.config.json            3-tier memory config
│   ├── openclaw.config.json         heartbeat schedules
│   ├── system_prompt.md             the agent's identity
│   └── gcp/                         ----- GCP deployment -----
│       ├── ARCHITECTURE.md          topology decisions + cost estimate
│       ├── README.md                step-by-step deployment guide
│       ├── main.tf                  Terraform: VM, SA, secrets, bucket, firewall
│       ├── startup.sh               VM bootstrap (Docker, Ops Agent, backups)
│       ├── deploy.sh                upload stack via IAP, start containers
│       └── terraform.tfvars.example fill in project_id + anthropic_api_key
├── .env.example
├── requirements.txt
└── .gitignore
```

## Getting started — local

Full host-install steps: **[`docs/install.md`](docs/install.md)**.

Quick path:

```bash
# Prereqs
brew install node@24 python@3.12

# 1. OpenClaw (agent runtime) on the host
npx openclaw onboard
openclaw plugins install @memtensor/memos-local-openclaw-plugin@latest
openclaw gateway restart

# 2. OpenSpace (skill runtime) — wired into OpenClaw via MCP
git clone --filter=blob:none --sparse https://github.com/HKUDS/OpenSpace.git
cd OpenSpace && git sparse-checkout set '/*' '!assets/' && pip install -e . && cd ..

# 3. Mini.ai's own Python deps (for tests + policy logic)
cp .env.example .env                       # fill in ANTHROPIC_API_KEY
pip install -r requirements.txt
pytest tests/                              # no services needed
```

Then edit `~/.openclaw/openclaw.json` to register OpenSpace as an MCP server pointing at `Mini.ai/skills/`. See `docs/install.md` step 3 for the exact JSON.

## Getting started — GCP

GCP deploy is **deferred to Phase 2**. The current `infra/gcp/` files were written against the old (broken) Docker stack and do not match the host-install path. Track this under [TODO.md](TODO.md) → S048–S052.

## Reading order

1. `docs/01-product-brief.md` — what and why
2. `docs/02-capabilities.md` — what it must do
3. `docs/03-design.md` — how it's built
4. `backlog.xlsx` — execution plan
5. `skills/*/SKILL.md` — the cognitive policies (specs)
6. `src/policies/*.py` — the cognitive policies (implementations)
7. `infra/gcp/ARCHITECTURE.md` — deployment rationale

## Status

- ✅ Docs complete (brief, capabilities, design)
- ✅ Backlog complete (13 epics, 56 stories, Sprint 0 plan, risks)
- ✅ All six policy SKILL.md specs written
- ✅ All six policies implemented in Python (logic only — integration glue pending)
- ✅ Salience + decay unit-tested (10 passing)
- ⚠️ Local Docker Compose stack — **superseded** by host install (Architecture L); see [`docs/04-deployment-reality.md`](docs/04-deployment-reality.md)
- ⚠️ GCP Terraform + startup + deploy scripts — **deferred to Phase 2**, currently does not match the host-install path
- ⏳ End-to-end host-install loop (Sprint 0 goal — see [`docs/install.md`](docs/install.md))
- ⏳ Reshape `src/policies/*.py` into proper OpenSpace skills (Sprint 0)
- ⏳ Skill-creation policy (E10 — P1, post-v0.1)
- ⏳ Parametric unlearning (E13 — research / P2)
