#!/bin/bash
# Upload stack files to the Mini.ai VM and start Docker Compose.
#
#   ./infra/gcp/deploy.sh                 # uses defaults
#   ./infra/gcp/deploy.sh --zone europe-west2-a --vm mini-ai

set -euo pipefail

ZONE="${ZONE:-europe-west2-a}"
VM="${VM:-mini-ai}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --zone) ZONE="$2"; shift 2 ;;
    --vm)   VM="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
echo "Repo root: $REPO_ROOT"
echo "Target: VM=$VM  zone=$ZONE"

# Package the stack files we need on the VM
STAGE="$(mktemp -d)"
mkdir -p "$STAGE/repo"
cp -r "$REPO_ROOT/infra/docker-compose.yml" "$STAGE/repo/"
cp    "$REPO_ROOT/infra/memos.config.json" "$STAGE/repo/"
cp    "$REPO_ROOT/infra/openclaw.config.json" "$STAGE/repo/"
cp    "$REPO_ROOT/infra/system_prompt.md" "$STAGE/repo/"
cp -r "$REPO_ROOT/skills" "$STAGE/repo/"
cp -r "$REPO_ROOT/src" "$STAGE/repo/"
cp    "$REPO_ROOT/requirements.txt" "$STAGE/repo/"

tar -czf "$STAGE/bundle.tar.gz" -C "$STAGE/repo" .

echo "Uploading via IAP..."
gcloud compute scp \
  --zone "$ZONE" \
  --tunnel-through-iap \
  "$STAGE/bundle.tar.gz" \
  "$VM:/tmp/bundle.tar.gz"

echo "Unpacking and starting stack on VM..."
gcloud compute ssh "$VM" \
  --zone "$ZONE" \
  --tunnel-through-iap \
  --command "
    sudo tar -xzf /tmp/bundle.tar.gz -C /var/lib/mini-ai/repo/
    cd /var/lib/mini-ai/repo
    sudo cp /var/lib/mini-ai/.env .env
    sudo docker compose -f docker-compose.yml pull || true
    sudo docker compose -f docker-compose.yml up -d
    sudo docker compose -f docker-compose.yml ps
  "

rm -rf "$STAGE"
echo ""
echo "Deploy complete."
echo ""
echo "Open a tunnel to talk to the agent:"
echo "  gcloud compute start-iap-tunnel $VM 7090 --local-host-port=localhost:7090 --zone=$ZONE"
echo ""
echo "SSH in for debugging:"
echo "  gcloud compute ssh $VM --tunnel-through-iap --zone=$ZONE"
