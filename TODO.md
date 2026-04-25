# Mini.ai — TODO

Living checklist. Works across sessions and terminals. Update by editing this file directly — `[ ]` becomes `[x]` when done. Commit after non-trivial changes so the next session sees current state.

**Status legend:** `[x]` done · `[ ]` open · `[~]` in progress · `[?]` blocked / needs decision

Last updated: 2026-04-25

---

## ✅ Phase 0 — Scaffolding (DONE)

- [x] Product brief, capabilities, design docs (`docs/`)
- [x] Backlog with 13 epics, 56 stories, Sprint 0 plan, risks (`backlog.xlsx`)
- [x] Six cognitive policy specs (`skills/<verb>/SKILL.md`)
- [x] Six cognitive policy implementations (`src/policies/`)
- [x] Pure-logic unit tests — 10 passing (`tests/test_pure_logic.py`)
- [x] Local Docker Compose stack (`infra/docker-compose.yml`)
- [x] GCP Terraform + startup + deploy scripts (`infra/gcp/`)
- [x] LICENSE (MIT) + CONTRIBUTING + README + CLAUDE.md
- [x] GitHub Actions CI (pytest on push)
- [x] Repo: github.com/sampathmaddali-14/Mini.ai

---

## 🔄 Sprint 0 — Make it actually run (4 weeks)

### Week 1 — Stack up locally
- [ ] **S001** — Get OpenClaw running via Docker Compose. Verify `docker compose ps` shows it Up.
- [ ] **S002** — CLI channel works. Send a message, get a response.
- [ ] **S005** — `.env.example` populated correctly; missing vars fail fast.
- [ ] **S006** — Qdrant container reachable from MemOS network.
- [ ] **S007** — Kuzu container running, basic node/edge round-trip works.
- [ ] **S008** — MemOS deployed with Qdrant + Kuzu config; API responds.
- [ ] **S012** — OpenSpace MCP server registered with OpenClaw.
- [ ] **S013** — Skills directory mounted; `skills list` returns the six policy stubs.

**Done when:** `docker compose up` brings everything up green; CLI channel works; MemOS API responds.

### Week 2 — Wire the basics
- [ ] **S003** — Heartbeat scheduler fires on cron schedules. At least 30m / daily / weekly schedules each invoke a test skill.
- [ ] **S004** — Structured logging: JSON lines with trace_id, policy, duration, outcome.
- [ ] **S009** — Official OpenClaw MemOS plugin installed and active. Pre-turn recall + post-turn capture happen automatically.
- [ ] **S010** — Memory inspector CLI works: `python -m src.core.inspect memories --last 20`.
- [ ] **S011** — Seed fixtures script loads ≥50 episodic + 10 semantic memories.
- [ ] **S014** — Policy SKILL.md template formalized; all six policies match.
- [ ] **S015** — Manual skill invocation works end-to-end with mock context.

**Done when:** A real conversation retrieves and writes memories; inspector CLI shows them; one heartbeat-triggered test skill runs successfully.

### Week 3 — Curation + Rewire foundations
- [ ] **S016** — Salience score function unit-tested (already done in `tests/test_pure_logic.py` ✓ but verify wired into curation path).
- [ ] **S017** — Threshold-gated writes: rejections logged with reason.
- [ ] **S018** — Near-duplicate detection: cosine > 0.92 triggers merge, not insert.
- [ ] **S021** — Entity extraction via LLM: extracted entities stored as Kuzu nodes.
- [ ] **S022** — Co-occurrence edges: `(A)-[:CO_OCCURS_WITH]->(B)` created with weight + sources.
- [ ] **S026** — Skill invocation tracking: SQLite logs success / failure / user_correction.
- [ ] **S027** — Skill quality EWMA score updates after each invocation.

**Done when:** New turns score for salience; duplicates merge; entity graph grows; skill scores update after each invocation.

### Week 4 — Close the loop
- [ ] **S019** — Contradiction detection (LLM-based) at curation time.
- [ ] **S020** — User override "remember this" bypasses curation filter.
- [ ] **S023** — Supersession: old fact marked superseded, new fact linked, both retained.
- [ ] **S028** — Reflection extracts insights from recent episodes; writes to semantic via curation.
- [ ] **S030** — Daily consolidation job summarizes yesterday's episodes into semantic memory.
- [ ] **S034** — Decay scoring updated on each access.
- [ ] **S045** — Policy firing log emits structured JSON for every firing.
- [ ] **S047** — `/healthz` endpoint returns 200 when L1-L3 services reachable.

**Done when:** Synthetic contradiction test passes; nightly job produces a semantic memory; health check green; policy logs emitted on every firing.

---

## 🚀 Post-Sprint-0

### Phase 1b — Hardening
- [ ] **S024** — Orphan node cleanup on pruning.
- [ ] **S025** — Path-based "why X Y" query.
- [ ] **S029** — Deprecate skills with quality < 0.3 over 10 invocations.
- [ ] **S031** — Confidence scoring for semantic memories.
- [ ] **S032** — Long-term tier promotion (confidence > 0.8 + age > 14d + accessed ≥ 2x).
- [ ] **S035** — Weekly pruning pass actually deletes (currently dry-run only safe).
- [ ] **S036** — Cascade graph cleanup verified end-to-end.
- [ ] **S037** — Deletion audit log + 7-day grace window.
- [ ] **S038** — User "forget X" command on CLI and chat.
- [ ] **S039** — Tombstones written on every deletion.
- [ ] **S040** — `undelete <id>` recovery within grace window.
- [ ] **S046** — Memory inspector web UI (FastAPI + minimal HTML).

### Phase 2 — Skill auto-generation (E10)
- [ ] **S041** — Novel-task detection (embedding mismatch against skill library).
- [ ] **S042** — Skill generation from successful trajectory (LLM-produced, lint + test pass).
- [ ] **S043** — Self-verification on 2 held-out cases before promotion.
- [ ] **S044** — Naming + dedup at creation time.

### Phase 2 — GCP deployment (E12)
- [ ] **S048** — GCP picked ✓ (decision recorded in `infra/gcp/ARCHITECTURE.md`).
- [ ] **S049** — `terraform apply` brings up VM + storage + IAM.
- [ ] **S050** — Secret Manager wired; no .env on disk in production.
- [ ] **S051** — TLS via reverse proxy (Caddy) — currently IAP-only, no TLS needed but worth adding for the messaging channels.
- [ ] **S052** — Backup script proven: restore on a fresh host produces working agent.

### Phase 2 — Parametric learning (E13, research-grade)
- [ ] **S053** — Pick base model for LoRA (Qwen / Llama variant).
- [ ] **S054** — Training data pipeline from semantic memory tier.
- [ ] **S055** — Retention-controlled LoRA update with KL bound.
- [ ] **S056** — Pre/post checkpoint A/B with regression gate.

---

## 🔓 Open decisions / questions

- [?] **Channel choice** — CLI is enough for v0.1, but Telegram or local web UI second? Decide before Week 2.
- [?] **Cheap-model provider** — Use Claude Haiku for entity extraction / salience LLM ops, or self-host a small model? Cost vs latency tradeoff. Default: Haiku.
- [?] **Embedding model for MemOS** — `bge-m3` is in the config; verify it actually loads in the MemOS container or pick alternative.
- [?] **Kuzu vs ArangoDB fallback** — Kuzu is the primary choice. Open: confirm Kuzu's REST wrapper image works as expected. If not, fall back to ArangoDB Community.

---

## 🧪 Testing milestones

- [x] Salience scoring unit-tested
- [x] Decay function unit-tested
- [ ] Curation policy integration test (mocked MemOS)
- [ ] Rewire policy integration test (real Kuzu)
- [ ] Contradiction detection eval (synthetic test set, target ≥95% correct)
- [ ] Preference recall eval (target 90% of week-1 prefs recalled by week 4)
- [ ] Pruning dry-run on seeded dataset (verify ≥20% pruned by day 30)
- [ ] 24hr autonomy test (heartbeat jobs ≥99% success)

---

## 📝 Notes for next session

Update this section as you go. Anything that would help future-you (or another Claude session) pick up the thread.

- **Working environment:** Repo at `github.com/sampathmaddali-14/Mini.ai`. Python 3.12. Docker Compose for local. GCP for deploy.
- **Currently iterating from:** _(fill in: laptop / phone / Claude Code / Claude.ai / iOS app)_
- **Last thing worked on:** _(fill in)_
- **Blockers:** _(fill in)_
- **Next concrete action:** _(fill in — keep this to one sentence)_

---

## How to use this file

- Edit it directly. Tick boxes as you complete things.
- Commit after meaningful updates so the file's git history shows progress.
- When starting a new session (any tool, any device), read this first. Combined with `CLAUDE.md`, it's full context.
- Don't let this file rot — if a story is no longer relevant, delete it; don't accumulate ghost TODOs.
