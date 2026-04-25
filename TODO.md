# Mini.ai — TODO

Living checklist. Works across sessions and terminals. Update by editing this file directly — `[ ]` becomes `[x]` when done. Commit after non-trivial changes so the next session sees current state.

**Status legend:** `[x]` done · `[ ]` open · `[~]` in progress · `[?]` blocked / needs decision

Last updated: 2026-04-25 (post-Architecture-L pivot)

---

## ✅ Phase 0 — Scaffolding (PARTIAL — see notes)

- [x] Product brief, capabilities, design docs (`docs/`)
- [x] Backlog with 13 epics, 56 stories, Sprint 0 plan, risks (`backlog.xlsx`)
- [x] Six cognitive policy specs (`skills/<verb>/SKILL.md`)
- [x] Six cognitive policy implementations (`src/policies/`) — **logic only; integration glue pending**
- [x] Pure-logic unit tests — 10 passing (`tests/test_pure_logic.py`)
- [~] ~~Local Docker Compose stack~~ → **superseded by host install (Architecture L)**. Compose now keeps Qdrant/Kuzu only as optional Phase 1b storage. See [`docs/install.md`](docs/install.md).
- [~] ~~GCP Terraform + startup + deploy scripts~~ → **deferred to Phase 2.** Current files reference the broken Docker stack.
- [x] LICENSE (MIT) + CONTRIBUTING + README + CLAUDE.md
- [x] GitHub Actions CI (pytest on push)
- [x] Repo: github.com/sampathmaddali-14/Mini.ai

---

## 🔄 Sprint 0 — Host-install end-to-end loop (4 weeks)

> Reset 2026-04-25 after S001 failed (3 of 5 Docker images don't exist on Hub). New plan follows Architecture L — host install of OpenClaw + MemOS Local plugin + OpenSpace. See [`docs/04-deployment-reality.md`](docs/04-deployment-reality.md) for the rationale and [`docs/install.md`](docs/install.md) for the actual commands.

### Week 1 — Host install
- [x] **S001** — OpenClaw 2026.4.23 installed and running under Node 24 (launchd-managed). Onboarding completed; gateway listening on `127.0.0.1:18789`. _2026-04-25_
- [x] **S002** — Web chat (Dashboard Control UI) working — replaced WhatsApp from initial onboarding. Real conversations observed in logs. _2026-04-25_
- [x] **S005** — `.env.example` populated correctly; missing vars fail fast.
- [x] **S009** — MemOS Local OpenClaw plugin installed (`@memtensor/memos-local-openclaw-plugin@1.0.9`), enabled in `~/.openclaw/openclaw.json`. SQLite store provisioned. **Pre-turn recall hook live** (auto-recall fires every turn, embedding model loaded). **Post-turn capture hook blocked** by an OpenClaw config-validator/loader inconsistency on `plugins.entries.*.hooks.allowConversationAccess` — workaround: agent uses explicit `memory_write_public` tool when user says "remember this". _2026-04-25_
- [x] **S012** — OpenSpace cloned (`~/OpenSpace`), installed via Python 3.12 venv (`~/OpenSpace/.venv`), `openspace-mcp` available. Registered in OpenClaw via `openclaw mcp set openspace ...`. `OPENSPACE_HOST_SKILL_DIRS` points at `~/Downloads/mini-ai/skills`. _2026-04-25_
- [ ] **S013** — Verify behavioral: from OpenClaw dashboard, agent calls OpenSpace `search_skills` and returns the 6 cognitive policies plus `delegate-task` + `skill-discovery` host skills. Pending live test.

**Done when:** OpenClaw gateway is up, CLI channel responds, the MemOS plugin recalls a `remember this` memory in a fresh turn, and OpenSpace lists our skills.

> ~~S006, S007, S008~~ — **deferred to Phase 1b.** The MemOS Local plugin includes its own SQLite + FTS5 + vector pipeline, so separate Qdrant / Kuzu / MemOS-as-service containers are not part of v0.1.

### Week 2 — Skill schema + memory verification
- [ ] **S003** — Heartbeat scheduler. **Open question:** is OpenClaw's gateway cron-capable, or do we run a small `apscheduler` daemon in `src/core/heartbeat.py`? Decide by end of Week 1.
- [ ] **S004** — Structured logging (JSON, trace_id, policy, duration, outcome) wherever we own code.
- [ ] **S010** — Memory inspector CLI: read the MemOS plugin's SQLite store and show recent memories. Replaces the original `src/core/inspect.py` (which assumed an HTTP MemOS service that doesn't exist).
- [ ] **S011** — Seed fixtures script loads ≥50 episodic + 10 semantic memories via the plugin's add-memory API.
- [ ] **S014** — Compare our SKILL.md frontmatter (`triggers`, `inputs`, `outputs`) with OpenSpace's actual schema (just `name` + `description` per `delegate-task`). Decide: keep extra fields as Mini.ai-internal documentation, or align strictly with upstream.
- [ ] **S015** — Manual end-to-end skill invocation: agent calls a Mini.ai policy via OpenSpace's `execute_task`, the policy runs, the result is captured in plugin memory.

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
- **Currently iterating from:** Claude Code on macOS (worktree).
- **Last thing worked on:** Got OpenClaw + MemOS Local plugin + OpenSpace all running on host (S001/S002/S005/S009/S012 ticked). Surfaced an OpenClaw upstream bug on `plugins.entries.*.hooks.allowConversationAccess` (validator vs loader inconsistency) — needs filing.
- **Blockers:** None blocking forward motion. Auto-capture deferred behind explicit `memory_write_public` tool path until upstream bug fix.
- **Next concrete action:** S013 behavioral test — in dashboard, ask the agent to "list skills via OpenSpace" and confirm `search_skills` returns the 6 cognitive policies + 2 host skills. Then wire the cognitive policies as proper OpenSpace skills (S014/S015).

---

## How to use this file

- Edit it directly. Tick boxes as you complete things.
- Commit after meaningful updates so the file's git history shows progress.
- When starting a new session (any tool, any device), read this first. Combined with `CLAUDE.md`, it's full context.
- Don't let this file rot — if a story is no longer relevant, delete it; don't accumulate ghost TODOs.
