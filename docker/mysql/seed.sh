#!/bin/bash
# Run seed scripts against the running MySQL container
# Usage: ./docker/mysql/seed.sh

set -e

echo "Running seed data..."
docker compose exec mysql sh -c 'mysql -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < docker/mysql/init/01-seed-data.sql
echo "Seed data applied."

echo "Ensuring admin role for chaldea@admin.com..."
docker compose exec mysql sh -c 'mysql -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < docker/mysql/init/02-ensure-admin.sql
echo "Admin check complete."
