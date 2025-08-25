#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Wait for main MySQL to be ready
echo "Waiting for MySQL..."
while ! nc -z ${MYSQL_HOST} ${MYSQL_PORT}; do
  sleep 1
done
echo "MySQL is up."

# Wait for auth MySQL to be ready (if configured)
if [ -n "${AUTH_MYSQL_HOST}" ] && [ -n "${AUTH_MYSQL_PORT}" ]; then
  echo "Waiting for Auth MySQL..."
  while ! nc -z ${AUTH_MYSQL_HOST} ${AUTH_MYSQL_PORT}; do
    sleep 1
  done
  echo "Auth MySQL is up."
fi

# Run backend (Python) database migrations
echo "Running backend migrations..."
alembic -c alembic.ini upgrade head
echo "Backend migrations complete."

# Run BetterAuth migrations (Node/Next.js) if available
if [ -d "/app/frontend" ]; then
  echo "Running BetterAuth migrations..."
  cd /app/frontend
  # Ensure node_modules exists (in image it does); fallback install if missing
  if [ ! -d "node_modules" ]; then
    npm ci --no-audit --no-fund || true
  fi
  node ./node_modules/@better-auth/cli/dist/index.mjs migrate --config ./authentication/server_auth.ts --yes
  echo "BetterAuth migrations complete."
  cd /app
fi

# Hand over to the main container command (CMD)
echo "Starting application..."
exec "$@" 