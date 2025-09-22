FROM apache/airflow:2.8.1

# Switch to root to install system-level packages
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev \
        build-essential \
        g++ \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements file while still root
COPY airflow/requirements.txt .

# --- FIX HERE ---
# Run all pip installs as root to allow compilation
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir requests

RUN pip install apache-airflow-providers-google --force-reinstall 


# Switch back to the non-privileged airflow user for runtime
USER airflow

# Copy shared modules needed by DAGs
COPY shared /opt/airflow/shared
COPY papers /opt/airflow/papers
COPY users /opt/airflow/users
COPY paperprocessor /opt/airflow/paperprocessor