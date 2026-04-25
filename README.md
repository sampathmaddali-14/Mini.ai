# Mini.ai

A brain-mimicking agentic architecture that can **create, curate, refine, rewire, learn, and unlearn** — approximating the functional patterns of human cognition rather than literal neural mimicry.

## Stack

All components are permissively licensed (MIT / Apache 2.0). Zero copyleft. Deployable on any hyperscaler; GCP is the current target.

| Layer | Component | License |
|---|---|---|
| Orchestration | OpenClaw | MIT |
| Memory OS | MemOS | Apache 2.0 |
| Skill library | OpenSpace | Permissive |
| Vector store | Qdrant | Apache 2.0 |
| Graph store | Kuzu | MIT |
| Reasoning | Claude API | N/A (hosted) |

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

```bash
cp .env.example .env                        # fill in ANTHROPIC_API_KEY
docker compose -f infra/docker-compose.yml up -d
pip install -r requirements.txt

# Sanity check
python -m src.core.cognitive_loop           # pings services
python -m src.core.cognitive_loop --seed    # loads fixture memories

# Fire policies manually
python -m src.core.run_policy curation --content "I prefer Docker Compose"
python -m src.core.run_policy rewire --mode sweep
python -m src.core.run_policy reflection
python -m src.core.run_policy pruning --dry-run

# Unit tests (no services needed)
pytest tests/
```

## Getting started — GCP

```bash
cd infra/gcp
cp terraform.tfvars.example terraform.tfvars   # set project_id + anthropic_api_key
terraform init && terraform apply
cd ../..
./infra/gcp/deploy.sh                           # uploads stack via IAP
gcloud compute start-iap-tunnel mini-ai 7090 --local-host-port=localhost:7090 --zone=europe-west2-a
```

Full guide: `infra/gcp/README.md`. Architecture rationale: `infra/gcp/ARCHITECTURE.md`.

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
- ✅ All six policy specs written (SKILL.md)
- ✅ All six policies implemented in Python
- ✅ Salience + decay unit-tested (10 passing)
- ✅ Local Docker Compose stack
- ✅ GCP Terraform + startup + deploy scripts
- ⏳ End-to-end integration test (Sprint 0 goal)
- ⏳ Skill-creation policy (E10 — P1, post-v0.1)
- ⏳ Parametric unlearning (E13 — research / P2)
