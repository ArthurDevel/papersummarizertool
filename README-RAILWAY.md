# Railway Deployment

## Approach
We use **one Dockerfile** for all 3 Airflow services (init, webserver, scheduler) with **different start commands** per Railway service.

**Why single Dockerfile:**
- Matches local development pattern (docker-compose uses same image)
- Easier maintenance (change dependencies once, not 3 times)
- Keeps hot-reloading developer experience intact - see [local development setup](README-LOCALDEVELOPMENT.md)

Some setup that is happening inside `docker-compose.yml` now needs to happen on Railway (see start commands below)

## Airflow Services

**Environment Variables:**
Add this to ALL Airflow containers on Railway:

```
RAILWAY_DOCKERFILE_PATH=airflow/Dockerfile
```

**CRITICAL:** If your DAGs import modules that require environment variables (like database credentials, API keys, etc.), you MUST add those environment variables to the **airflow-scheduler** service specifically. The scheduler is where DAGs actually execute - the webserver only provides the UI.


**Start Commands:**
Add these to each Airflow container.
- **airflow-init**: `bash -c "airflow db init && airflow users create --username admin --password admin --firstname Anonymous --lastname User --role Admin --email admin@example.org && echo 'Initialization complete' && exit 0"`
- **airflow-webserver**: `airflow webserver`
- **airflow-scheduler**: `airflow scheduler`
