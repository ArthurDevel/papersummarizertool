#!/bin/bash

# Set up volume permissions if directory exists
if [ -d "/opt/airflow-data" ]; then
    sudo mkdir -p /opt/airflow-data/{dags,logs,plugins}
    # Use just the airflow user, not group (Railway may not have airflow group)
    sudo chown -R airflow /opt/airflow-data
    sudo chmod -R 755 /opt/airflow-data
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
