#!/bin/sh
set -e

# Retry the migration until the (external) database is reachable, so a brief DB
# unavailability at cold start becomes a clean wait instead of a crash-loop.
echo "[entrypoint] running DB migration (with readiness retry)..."
i=1
until node dist/migrate.js; do
  if [ "$i" -ge 20 ]; then
    echo "[entrypoint] database still unreachable after $i attempts; giving up." >&2
    exit 1
  fi
  echo "[entrypoint] migration attempt $i failed (DB not ready?); retrying in 3s..."
  i=$((i + 1))
  sleep 3
done

echo "[entrypoint] seeding admin (idempotent)..."
node dist/seed-admin.js

echo "[entrypoint] starting Next.js standalone server..."
exec node server.js
