# Railway Deployment

## Approach
We use **one Railway service** that runs init, webserver, and scheduler using **supervisord** because Railway doesn't support shared volumes between services.

**Why single service:**
- Railway limitation: No shared volumes between separate services  
- Solves log visibility issue (scheduler writes logs, webserver reads them)

## Single Airflow Service Setup

**Environment Variables:**
Add these to your Railway Airflow service:

```
RAILWAY_DOCKERFILE_PATH=airflow/Dockerfile
AIRFLOW__CORE__EXECUTOR=LocalExecutor
AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow-data/dags 
AIRFLOW__LOGGING__BASE_LOG_FOLDER=/opt/airflow-data/logs
AIRFLOW__CORE__PLUGINS_FOLDER=/opt/airflow-data/plugins
```

**Volume Mount:**
- Mount Railway volume at: `/opt/airflow-data`
- Contains: dags, logs, plugins

**Start Command:**
- Leave empty (uses entrypoint automatically)

**What It Does:**
1. Sets up volume permissions  
2. Copies DAGs from `/opt/airflow/dags` to `/opt/airflow-data/dags` (volume path changed)
3. Sets Python path for shared modules (shared, papers, users, paperprocessor)
4. Initializes database (`airflow db init`)
5. Creates admin user (admin/admin)
6. Starts both scheduler and webserver via supervisord

**CRITICAL:** Add your DAG environment variables (database credentials, API keys, etc.) to this service since both scheduler and webserver run here.

## Troubleshooting

**Common Issues:**

- **Protobuf version conflict** - Add `protobuf==3.20.3` to requirements.txt if you see Google Cloud import errors
- **Sudo permission errors** - Railway doesn't support sudo; entrypoint now handles permissions gracefully  
- **SequentialExecutor instead of LocalExecutor** - Make sure `AIRFLOW__CORE__EXECUTOR=LocalExecutor` is set
- **Missing airflow group** - Use `chown airflow` instead of `chown airflow:airflow` on Railway
- **Log visibility issues** - Ensure volume is mounted at `/opt/airflow-data` and path env vars are set
- **Supervisord privilege errors** - Remove `user=root` from supervisord.conf, let it run as airflow user
- **DAGs not showing up** - Dockerfile copies DAGs to `/opt/airflow/dags` but we remapped to `/opt/airflow-data/dags`; entrypoint copies them to volume path
- **Module import errors in DAGs** - Python path includes shared modules; rebuild if imports still fail
