#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Wait for MySQL to be ready
echo "Waiting for MySQL..."
while ! nc -z ${MYSQL_HOST} ${CONTAINERPORT_MYSQL}; do
  sleep 1
done
echo "MySQL is up."

# Run database migrations
echo "Running database migrations..."
alembic -c alembic.ini upgrade head
echo "Migrations complete."

# Hand over to the main container command (CMD)
echo "Starting application..."
exec "$@" 