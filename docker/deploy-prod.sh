#!/usr/bin/env bash
# Production deploy. Runs on the VPS, started detached by CI (or by hand):
#   nohup bash ~/deploy/deploy-prod.sh <run-id> > ~/deploy/<run-id>.log 2>&1 &
#
# Why it looks like this:
# - Images are built BEFORE any container is touched. A failed build leaves the
#   running site as it was; the old script ran `down` first and a broken build
#   left prod offline.
# - One image at a time, with the layer cache. The VPS has ~4 GB RAM and no
#   swap; building all images in parallel with --no-cache starved it until sshd
#   stopped answering.
# - Detached from the SSH session, so a dropped connection cannot kill it
#   halfway. CI polls <run-id>.exit for the result.
set -euo pipefail

RUN_ID="${1:-manual-$(date +%Y%m%d-%H%M%S)}"
REPO_DIR="${REPO_DIR:-$HOME/rpgroll}"
STATE_DIR="$HOME/deploy"
LOCK_FILE=/tmp/chaldea-deploy.lock
LOCK_WAIT_SECONDS=3600
# Backends run migrations on start and may restart while MySQL comes up; nginx
# resolves upstream names once, so without a reload it keeps their old IPs
# and answers 502
NGINX_RELOAD_DELAY_SECONDS=60
BUILD_CACHE_KEEP=168h
LOG_KEEP_DAYS=30

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

mkdir -p "$STATE_DIR"
trap 'echo $? > "$STATE_DIR/$RUN_ID.exit"' EXIT

log() { echo "=== $(date -u +%H:%M:%S) $*"; }

# Two pushes in a row must not build over each other
exec 9>"$LOCK_FILE"
log "waiting for deploy lock"
flock -w "$LOCK_WAIT_SECONDS" 9

cd "$REPO_DIR"
git fetch origin main
git reset --hard origin/main
log "deploying $(git log -1 --format='%h %s')"

for service in $("${COMPOSE[@]}" config --services); do
  log "build $service"
  "${COMPOSE[@]}" build "$service"
done

log "up"
"${COMPOSE[@]}" up -d

log "waiting ${NGINX_RELOAD_DELAY_SECONDS}s before nginx reload"
sleep "$NGINX_RELOAD_DELAY_SECONDS"
docker exec api-gateway nginx -t
docker exec api-gateway nginx -s reload

log "cleanup"
docker image prune -f
docker builder prune -f --filter "until=$BUILD_CACHE_KEEP"
find "$STATE_DIR" -type f -mtime +"$LOG_KEEP_DAYS" -delete

log "DONE"
