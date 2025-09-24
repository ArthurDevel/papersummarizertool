FROM apache/airflow:2.10.1-python3.11

# Switch to root to install system-level packages
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev \
        build-essential \
        g++ \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Switch to airflow user before pip installs
USER airflow

# Copy requirements file
COPY airflow/requirements.txt .

# Run pip installs as airflow user without --user flag
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir requests

# Copy DAGs and shared modules
COPY airflow/dags /opt/airflow/dags
COPY shared /opt/airflow/shared
COPY papers /opt/airflow/papers
COPY users /opt/airflow/users
COPY paperprocessor /opt/airflow/paperprocessor

# Make sure PATH includes airflow binaries
ENV PATH="/home/airflow/.local/bin:$PATH"

# Expose port 8080 for webserver (doesn't affect scheduler/init services)
EXPOSE 8080

# No CMD - Railway will handle different start commands per service