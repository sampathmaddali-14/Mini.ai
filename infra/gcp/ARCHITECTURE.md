# Mini.ai on GCP — Architecture

## Deployment decision: hybrid GCE + Cloud Run

**Stateful, always-on services** run on a single **Compute Engine VM** (e2-standard-4, Debian 12):
- OpenClaw (needs persistent daemon, heartbeat, local state)
- MemOS, OpenSpace (stateful, need filesystem persistence)
- Qdrant (vector store, persistent disk)
- Kuzu (embedded graph, persistent disk)
- SQLite stores (skill quality, tombstones)

**Stateless policy runners** (future expansion) can run on **Cloud Run** if we need horizontal scale. For v0.1, everything is on the VM.

## Why not Cloud Run for everything
Cloud Run is stateless and scales to zero — great for cost, bad for:
1. Persistent daemon with heartbeat (not a request/response fit).
2. Embedded Kuzu database (needs a local filesystem that survives).
3. OpenSpace skill workspace (accumulates state).
Attempting to use Cloud Run forces Cloud SQL + Memorystore + Filestore, which quintuples the cost and complexity for a single-user system.

## Why not GKE
GKE is overkill for a single-user agent. The ops overhead of Kubernetes isn't justified until you're running ≥5 stateful workloads or need multi-tenant isolation.

## Services used

| GCP Service | Purpose | Tier/Size |
|---|---|---|
| Compute Engine | Agent host | e2-standard-4 (4 vCPU, 16 GB RAM), Debian 12 |
| Persistent Disk | Stateful volumes | 200 GB pd-balanced |
| Artifact Registry | Private container images | Standard tier |
| Secret Manager | ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN | — |
| Cloud Scheduler | Backup job trigger | — |
| Cloud Storage | Nightly DB backups | Nearline class |
| Cloud Logging | Structured logs aggregation | Default |
| Cloud Monitoring | Health check, alerts | Default |
| Cloud DNS (opt.) | mini.example.com → VM | — |
| IAM | Service account minimum perms | — |

## Identity and secrets

- **Workload identity:** VM runs as a dedicated service account `mini-ai-sa` with only the permissions it needs — Secret Manager reader (specific secrets), Cloud Storage writer (backup bucket only), Logging writer.
- **Secrets:** `ANTHROPIC_API_KEY` stored in Secret Manager. Mounted via a startup script or the Secret Manager CSI driver pattern — never baked into images.
- **No public IP for services.** Docker publishes only to `127.0.0.1`. Access from outside is via SSH tunnel or Cloud IAP TCP forwarding (no public ports).
- **Firewall:** `deny-all` ingress except SSH via IAP. Egress allowed only to Anthropic API and GCP-managed services.

## Network and access

- VPC: default VPC is fine for v0.1 (single-user). Phase 2: dedicated VPC with egress NAT.
- Ingress to the agent: **IAP TCP forwarding** — `gcloud compute start-iap-tunnel mini-ai 7090` opens a port locally. Better than SSH tunneling for multi-port access.
- Egress to Claude API: allowed via NAT (or direct — Anthropic API is `api.anthropic.com`).
- Telegram (optional channel): outbound only.

## Storage and backups

- Primary data on the VM's persistent disk at `/var/lib/mini-ai/`.
- Nightly backup (03:00 UTC) runs on the VM via cron: tars `/var/lib/mini-ai/`, uploads to `gs://mini-ai-backups-<project>/`.
- Cloud Storage lifecycle: move to Coldline after 30 days, delete after 180 days.
- Restore: one command — `./infra/gcp/restore.sh <backup-object>`.

## Observability

- OpenClaw writes JSON logs to `/var/lib/mini-ai/logs/`.
- Google Ops Agent on the VM tails those logs into Cloud Logging with structured fields (policy, trace_id, duration).
- Cloud Monitoring uptime check against `/healthz` on the VM via IAP.
- Alert: any heartbeat job with `ok=false` in the last 2 hours.

## Cost estimate (single-user)

| Line item | Monthly USD |
|---|---|
| e2-standard-4 VM (24/7) | ~96 |
| pd-balanced 200 GB | ~24 |
| Cloud Storage (Nearline 5 GB avg) | ~0.05 |
| Secret Manager (1 secret, few accesses) | ~0 |
| Cloud Logging (small volume) | ~0 |
| Egress (mostly API, ~10 GB/month) | ~1 |
| Claude API usage | variable, not GCP |
| **Total GCP infra** | **~120/month** |

The VM dominates. If cost is tight: e2-standard-2 (~50/mo) works but squeezes MemOS headroom. Preemptible VMs aren't appropriate for a memory-backed agent.

## Regions

- Pick a region close to you for latency: **europe-west2** (London) for Plumstead-based user, or **europe-west4** (Netherlands) as a close second with slightly lower costs.
- Keep everything in one region for v0.1. Multi-region is a Phase-3 problem.

## What we are deliberately NOT doing (and why)

| Tempting choice | Why we skip |
|---|---|
| Cloud Run for policies | Stateless model fights the daemon pattern |
| Cloud SQL for MemOS backing | MemOS owns its storage; don't double-layer |
| Memorystore/Redis | No current need; adds ops overhead |
| GKE | Single workload; overkill |
| Vertex AI for reasoning | We use Claude API; Vertex adds a layer |
| Load balancer | Single user, no public endpoint |
| VPC Service Controls | Premium feature; revisit if multi-user |

## Phase 2 changes (not now)

- Separate VPC with private Google access and NAT gateway.
- Cloud IAP + IAM for multi-user auth.
- Move MemOS Qdrant to managed Qdrant Cloud if embedding volume grows (still Apache 2.0).
- Promote backup to continuous WAL-style replication for Kuzu.
- Terraform state in GCS backend with object versioning.
