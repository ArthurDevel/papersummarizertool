FROM apache/airflow:2.8.1

# Switch to root to install system-level packages
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends default-libmysqlclient-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Switch back to the non-privileged airflow user
USER airflow

# Copy and install the Airflow-specific Python requirements
COPY airflow/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install any additional packages needed by DAGs
RUN pip install --no-cache-dir requests

# Copy shared modules needed by DAGs
COPY shared /opt/airflow/shared
COPY papers /opt/airflow/papers
COPY users /opt/airflow/users
COPY paperprocessor /opt/airflow/paperprocessor
