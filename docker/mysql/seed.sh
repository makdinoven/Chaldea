#!/bin/bash
# Run seed scripts against the running MySQL container
# Usage: ./docker/mysql/seed.sh
#
# IMPORTANT: mysql client in batch mode aborts on the first error by default.
# A single failing INSERT (e.g. a schema-drift column mismatch or a missing
# table because an Alembic migration hasn't run yet) silently skips every
# statement after it, leaving tables partially empty. We use --force to make
# mysql continue past errors AND --verbose so errors are visible on stderr.
# The script itself still exits 0 on per-statement errors — check the output.

set -e

SEED_CMD='mysql --force --show-warnings -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"'

echo "Running seed data..."
docker compose exec -T mysql sh -c "$SEED_CMD" < docker/mysql/init/01-seed-data.sql
echo "Seed data applied."

echo "Ensuring admin role for chaldea@admin.com..."
docker compose exec -T mysql sh -c "$SEED_CMD" < docker/mysql/init/02-ensure-admin.sql
echo "Admin check complete."
