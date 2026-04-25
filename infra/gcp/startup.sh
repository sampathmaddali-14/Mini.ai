#!/bin/bash
# Mini.ai VM startup script.
# Runs on first boot. Installs Docker, fetches secrets, starts the stack.

set -euo pipefail

exec > /var/log/mini-startup.log 2>&1
echo "[$(date -u)] Mini.ai startup script starting"

# ----- Install Docker -----
apt-get update -y
apt-get install -y ca-certificates curl gnupg jq cron

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# ----- Install Google Cloud Ops Agent for log aggregation -----
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
bash add-google-cloud-ops-agent-repo.sh --also-install

# ----- Configure Ops Agent to ship JSON logs from OpenClaw -----
cat > /etc/google-cloud-ops-agent/config.yaml <<'YAML'
logging:
  receivers:
    mini_ai:
      type: files
      include_paths: [/var/lib/mini-ai/logs/*.log]
      record_log_file_path: true
  service:
    pipelines:
      mini_ai:
        receivers: [mini_ai]
YAML
systemctl restart google-cloud-ops-agent || true

# ----- Create working directories -----
mkdir -p /var/lib/mini-ai/{logs,data,skills,repo}
chmod 755 /var/lib/mini-ai

# ----- Fetch secrets from Secret Manager -----
ANTHROPIC_KEY=$(gcloud secrets versions access latest --secret=mini-ai-anthropic-api-key 2>/dev/null || echo "")

if [[ -z "$ANTHROPIC_KEY" ]]; then
  echo "WARNING: Anthropic API key not available yet. Will fail at stack startup."
fi

# ----- Write .env for the Docker stack -----
cat > /var/lib/mini-ai/.env <<EOF
ANTHROPIC_API_KEY=${ANTHROPIC_KEY}
MEMOS_URL=http://memos:7070
OPENSPACE_MCP_URL=http://openspace:7080
QDRANT_URL=http://qdrant:6333
KUZU_URL=http://kuzu:8000
MEMOS_DEFAULT_MODEL=claude-opus-4-7
HEARTBEAT_ENABLED=true
LOG_LEVEL=info
SALIENCE_THRESHOLD=0.3
DECAY_HALF_LIFE_DAYS_EPISODIC=14
DECAY_HALF_LIFE_DAYS_SEMANTIC=180
EOF
chmod 600 /var/lib/mini-ai/.env

# ----- Copy the Docker Compose from the VM's metadata or a GCS drop -----
# In production: pull the repo via a deploy key or from a GCS bucket.
# For v0.1 we assume the operator runs `infra/gcp/deploy.sh` after `terraform apply`
# to upload the compose file and skills folder into /var/lib/mini-ai/repo.

# ----- Nightly backup cron -----
cat > /etc/cron.d/mini-ai-backup <<'CRON'
# Back up /var/lib/mini-ai to GCS nightly at 03:00 UTC
0 3 * * * root /usr/local/bin/mini-backup.sh >> /var/log/mini-backup.log 2>&1
CRON
chmod 644 /etc/cron.d/mini-ai-backup

cat > /usr/local/bin/mini-backup.sh <<'BASH'
#!/bin/bash
set -euo pipefail
PROJECT=$(curl -s "http://metadata.google.internal/computeMetadata/v1/project/project-id" -H "Metadata-Flavor: Google")
BUCKET="gs://${PROJECT}-mini-ai-backups"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

cd /var/lib/mini-ai
tar --exclude=logs -czf /tmp/mini-backup-${STAMP}.tar.gz data skills .env
gcloud storage cp /tmp/mini-backup-${STAMP}.tar.gz ${BUCKET}/
rm /tmp/mini-backup-${STAMP}.tar.gz
echo "[$(date -u)] Backup complete: ${STAMP}"
BASH
chmod 755 /usr/local/bin/mini-backup.sh

echo "[$(date -u)] Mini.ai startup script complete. Next: run deploy.sh to upload stack files."
