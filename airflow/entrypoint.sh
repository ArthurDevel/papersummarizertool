#!/bin/bash

# Set up volume permissions if directory exists
if [ -d "/opt/airflow-data" ]; then
    mkdir -p /opt/airflow-data/{dags,logs,plugins} 2>/dev/null || true
    # Skip ownership changes on Railway if they fail
    chmod -R 755 /opt/airflow-data 2>/dev/null || true
fi

# Initialize Airflow database and create admin user
echo "Initializing Airflow database..."
airflow db init

echo "Creating admin user..."
airflow users create \
    --username admin \
    --password admin \
    --firstname Anonymous \
    --lastname User \
    --role Admin \
    --email admin@example.org

echo "Starting Airflow scheduler and webserver..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
