# Mini.ai on GCP — Deployment Guide

## Prerequisites

- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- `terraform` >= 1.5 installed
- A GCP project with billing enabled (create via Console or `gcloud projects create`)
- Your Anthropic API key

## One-time project bootstrap

```bash
export PROJECT_ID=your-project-id
gcloud config set project $PROJECT_ID

# Link billing (required)
# Do this in the Console: https://console.cloud.google.com/billing

# Enable the minimum APIs Terraform needs to enable the rest
gcloud services enable compute.googleapis.com cloudresourcemanager.googleapis.com
```

## Deploy infrastructure

```bash
cd infra/gcp

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set project_id and anthropic_api_key

terraform init
terraform apply
```

Takes ~3-5 minutes. Creates the VM, service account, secrets, buckets, firewall rules.

## Upload the stack and start it

```bash
# From repo root
./infra/gcp/deploy.sh
```

The deploy script:
1. Tars `docker-compose.yml`, skills/, src/, config files.
2. Uploads via IAP TCP forwarding (no public IP needed on the VM).
3. Unpacks into `/var/lib/mini-ai/repo/` on the VM.
4. Runs `docker compose up -d`.

## Verify

```bash
# SSH into the VM via IAP (no public SSH port)
gcloud compute ssh mini-ai --tunnel-through-iap --zone=europe-west2-a

# On the VM:
cd /var/lib/mini-ai/repo
sudo docker compose ps         # all services Up
sudo docker compose logs openclaw --tail=50
cat /var/log/mini-startup.log  # startup script output
```

## Open a tunnel to the agent (from your laptop)

```bash
gcloud compute start-iap-tunnel mini-ai 7090 \
  --local-host-port=localhost:7090 \
  --zone=europe-west2-a
```

Now `curl http://localhost:7090/healthz` talks to OpenClaw on the VM.

## Update the stack after code changes

```bash
# Just re-run deploy — it's idempotent
./infra/gcp/deploy.sh
```

## Verify backups

```bash
# Trigger a backup manually
gcloud compute ssh mini-ai --tunnel-through-iap \
  --command "sudo /usr/local/bin/mini-backup.sh"

# List what's in the bucket
gcloud storage ls gs://${PROJECT_ID}-mini-ai-backups/
```

## Destroy everything (clean shutdown)

```bash
cd infra/gcp
terraform destroy
```

This removes the VM, disk, IAM bindings, secrets, firewall rules. **It does not delete the backup bucket** — that's deliberate, so you don't lose data during rebuilds. Delete it manually if you want:

```bash
gcloud storage rm -r gs://${PROJECT_ID}-mini-ai-backups/
gcloud storage buckets delete gs://${PROJECT_ID}-mini-ai-backups/
```

## Troubleshooting

**`Error: Error waiting for instance to create: The resource ... already exists`**
Run `terraform destroy` first, or import the existing resource.

**IAP tunnel hangs**
Make sure your user has `roles/iap.tunnelResourceAccessor` on the project. Also check firewall: the `mini-ai-allow-iap` rule must target IP range `35.235.240.0/20`.

**`gcloud compute ssh` fails with permission denied**
Enable OS Login on your user: `gcloud compute os-login ssh-keys add --key-file=~/.ssh/id_rsa.pub`, and ensure you have `roles/compute.osLogin`.

**Docker Compose fails on the VM**
SSH in, check `/var/log/mini-startup.log` and `sudo docker compose logs`. Most common cause: `.env` wasn't populated because Secret Manager access failed. Fix IAM binding, then:
```bash
gcloud secrets versions access latest --secret=mini-ai-anthropic-api-key
```
should succeed as the VM's service account (or add the binding if missing).

**API quota / model access**
If Claude API calls return 401, the key in Secret Manager is wrong or your Anthropic account doesn't have access to the model in `MEMOS_DEFAULT_MODEL`. Update the secret:
```bash
echo -n "sk-ant-new-key" | gcloud secrets versions add mini-ai-anthropic-api-key --data-file=-
```
Then re-run deploy (or restart containers on the VM).

## What this setup does NOT do (by design)

- No public IP / no public endpoint. Access is always via IAP.
- No load balancer, no CDN. Single-user system.
- No auto-scaling. One VM. If you restart the VM, the stack restarts with it.
- No managed database. MemOS owns its storage; we don't second-guess it.

Phase 2 adds Cloud NAT, private VPC, monitoring dashboards, and optional managed Qdrant.
