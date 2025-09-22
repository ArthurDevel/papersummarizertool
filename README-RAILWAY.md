# Railway Deployment

## Approach
We use **one Dockerfile** for all 3 Airflow services (init, webserver, scheduler) with **different start commands** per Railway service.

**Why single Dockerfile:**
- Matches local development pattern (docker-compose uses same image)
- Easier maintenance (change dependencies once, not 3 times)
- Seamless developer experience - see [local development setup](README-LOCALDEVELOPMENT.md)

**Alternative considered:** 3 separate Dockerfiles (rejected for complexity)

## Airflow Services

**Environment Variable:**
```
RAILWAY_DOCKERFILE_PATH=airflow/Dockerfile
```

**Start Commands:**
- **airflow-init**: `bash -c "airflow db init && airflow users create --username admin --password admin --firstname Anonymous --lastname User --role Admin --email admin@example.org && echo 'Initialization complete' && exit 0"`
- **airflow-webserver**: `airflow webserver`
- **airflow-scheduler**: `airflow scheduler`
