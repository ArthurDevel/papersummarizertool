# Local Development Setup

## At a glance
This project uses a "Develop Inside Docker" approach for a consistent and simple local development experience.
- `npm run dev` runs inside Docker for instant frontend changes
- `uvicorn api.main:app --reload` runs inside Docker for instant backend changes

## Starting development environment

### .env
Set up `.env` with your normal variables. `HOSTPORT_FRONTEND` and `HOSTPORT_API` can be used to override default settings in case a port is already used on your machine.

### Start environment

Do not use the right-click option that is built-in in Cursor, but rather use `docker-compose up --build`. This will make sure that `docker-compose.override.yaml` overrides the important bits.

### Accessing application

- frontend: `http://localhost:{HOSTPORT_FRONTEND:-3000}` 
- backend: `http://localhost:{HOSTPORT_API:-8000}` 

## Configuration

The [docker-compose.override.yaml](docker-compose.override.yaml) and [frontend/package.json](frontend/package.json) files handle the configuration. `npm-run-all` is used as a dependency.

The override file enables hot-reloading by mounting the entire project directory from your local machine into the container (except `/app/frontend/node_modules`). This means any file changes you make locally are instantly reflected inside the container, triggering the development servers to reload.