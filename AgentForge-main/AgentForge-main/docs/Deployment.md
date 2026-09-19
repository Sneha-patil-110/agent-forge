# Deployment

## What This Document Is

How AgentForge is actually built and run in production today: the backend's Docker image and its FastAPI Cloud deployment, the frontend's Vercel deployment, and the CORS/environment wiring that connects them. Unlike [System_Architecture.md](System_Architecture.md) (how the system is composed) this document is about how it's packaged and hosted.

**Live:** [frontend-naman-213.vercel.app](https://frontend-naman-213.vercel.app) (Vercel) &middot; [agentforge.fastapicloud.dev](https://agentforge.fastapicloud.dev) (FastAPI Cloud)

---

## Backend: Docker Image

`Dockerfile` (repo root) is a three-stage build, backend only; the frontend is never built or served by this image.

1. **`deps`** (`python:3.11-slim` + `build-essential`) installs `requirements.txt` into `/install` via `pip install --prefix`, so the compiler toolchain used to build any wheel without a prebuilt binary never ships in the final image.
2. **`node`** (`node:20-bookworm-slim`) exists only as a source to copy Node/npm binaries from. Debian's own `apt-get install nodejs npm` pulls in an unrelated build toolchain (webpack, babel, jest, node-gyp) as transitive dependencies, adding real image size and build time for packages the runtime never touches; copying the binaries directly avoids that.
3. **`runtime`** (`python:3.11-slim`) installs `git` (required because `GitTool` shells out to the `git` binary via GitPython) and `ca-certificates` (outbound HTTPS to LLM providers and HTTP-transport MCP servers), copies the Node binaries and installed Python packages from the earlier stages, copies `backend/`, `alembic/`, `alembic.ini`, creates the `workspace/`, `.agentforge/runs/`, and `logs/` directories the app writes to at runtime, and runs as a non-root `appuser` (uid 1000).

Node.js ships in the runtime image because the `playwright` MCP server is still `npx`-launched (see [MCP_Integration.md](MCP_Integration.md#nodejs-dependency-v17)), and because `TestDiscoveryService`'s Node test plan runs `npm test`/`npm run build` inside generated Node/React projects. The `filesystem`, `sequential-thinking`, and `postgres` MCP servers no longer need Node at all as of v1.7 (reimplemented in Python / switched to a pip package) specifically because **FastAPI Cloud does not use this Docker image** and has no Node.js in its own runtime — see below.

The container's `CMD` uses `sh -c "exec python -m uvicorn ..."` deliberately: `exec` replaces the shell process so uvicorn runs as PID 1 and receives `SIGTERM` directly, letting the FastAPI lifespan's shutdown path (`Application.ashutdown()`, closing every MCP client, disposing the DB engine, flushing tracing) run to completion instead of the container being killed outright. A `HEALTHCHECK` polls `/health` (no external dependency, only already-established application/DB state) every 30s.

`.dockerignore` excludes the frontend, all `.env*` files except `.env.example`, local virtualenvs, caches, `.git/`, generated runtime output (`workspace/`, `.agentforge/`, `logs/`, `summary/`), and `docs/`/`tests/`/`README.md` — none of it is needed at runtime.

```bash
docker build -t agentforge-backend .
docker run -p 8000:8000 --env-file .env agentforge-backend
```

Mount `workspace/`, `.agentforge/`, and `logs/` as volumes in any real deployment to persist generated projects and run history across container restarts; the image itself treats them as ephemeral.

**Verified**: a real container build, all 7 enabled MCP servers connecting successfully inside it, and a clean shutdown (zero `RuntimeError`s from MCP client teardown, the failure mode `Application.ashutdown()` exists specifically to avoid — see below) on `docker stop`.

## Backend: FastAPI Cloud

The production API at `agentforge.fastapicloud.dev` runs on [FastAPI Cloud](https://fastapicloud.com), not the Docker image above — FastAPI Cloud builds and runs the source directly via its own `uv`-based pipeline, reading `pyproject.toml`. Getting there required resolving several real, non-obvious build-pipeline behaviors, each verified by reproducing the exact failure locally before changing the real repo:

* **`fastapi[standard]` is a hard requirement**, not just `fastapi` — the `fastapi` CLI entrypoint FastAPI Cloud runs (`fastapi run backend.api.app:app`) doesn't exist in the base extra.
* **`pyproject.toml`'s `[project]` table triggers PEP 621 package-build semantics** on FastAPI Cloud's pipeline. `dependencies` is sourced dynamically from `requirements.txt` (`[tool.setuptools.dynamic]`) rather than duplicated, since FastAPI Cloud's early build stage doesn't have `setup.py`/full source available, only `pyproject.toml`/`requirements.txt`:
  ```toml
  [project]
  name = "agentforge"
  version = "0.1.0"
  requires-python = ">=3.11"
  dynamic = ["dependencies"]

  [tool.setuptools.dynamic]
  dependencies = {file = ["requirements.txt"]}

  [tool.fastapi]
  entrypoint = "backend.api.app:app"
  ```
* **GitPython imports the `git` binary eagerly at module load time.** If it's missing from `PATH` in the build/runtime environment, importing `backend.tools.git_tool` (and transitively the whole app) crashes before the server can even start. `GIT_PYTHON_REFRESH=quiet` is set as a FastAPI Cloud environment variable (not a code change — this is GitPython's own documented escape hatch) to avoid the crash. This is a disclosed, accepted tradeoff: git-based operations (`GitTool`) are non-functional in this environment as a result, the same way the database and MCP layers already degrade gracefully when a dependency isn't available.

Required environment variables on FastAPI Cloud: whichever LLM provider key(s) are in use, `JWT_SECRET`, `API_CORS_ORIGINS` (see below), `GIT_PYTHON_REFRESH=quiet`, and optionally `DATABASE_URL`/LangSmith tracing vars — all documented in [.env.example](../.env.example).

## Frontend: Vercel

The frontend (`frontend/`) deploys to Vercel from the same monorepo, with **Root Directory** set to `frontend` in Project Settings → Build and Deployment — required because the repo root also contains the Python backend, and without it Vercel's build can't find `frontend/package.json` or correctly resolve the `@/*` TypeScript path aliases (`frontend/tsconfig.json`) during the build.

GitHub-integration deploys (push to `main` triggers a build) and CLI deploys (`vercel --prod`, run from inside `frontend/`) are independent paths: the CLI path uploads the local working tree directly, while GitHub-integration clones from git. This distinction mattered once in practice — see the `.gitignore` note below.

```bash
cd frontend
vercel link          # one-time, links to the Vercel project
vercel --prod
```

**Environment variable**: `NEXT_PUBLIC_API_URL`, set to the production API origin (`https://agentforge.fastapicloud.dev`) in the Vercel project's environment settings. This is the only backend URL configured anywhere in the frontend; `frontend/src/lib/api.ts` is the single source every API call and SSE connection (`eventsStreamUrl()`) derives from, so there is nothing else to update if the backend origin ever changes. See [Frontend_Design.md](Frontend_Design.md).

### A real incident: `.gitignore` silently excluded `frontend/src/lib/`

The root `.gitignore`'s Python-packaging boilerplate included an unanchored `lib/` entry (meant for `build/lib/`, standard in any generated Python `.gitignore`). Without a leading slash, git matches that pattern against a directory named `lib` **anywhere** in the repository, not just at the root, so it silently excluded `frontend/src/lib/` (`api.ts`, `types.ts`, `utils.ts`, and four other files) from every commit. Every `@/lib/...` import in the frontend depends on that directory.

This went unnoticed for a while because CLI deploys (`vercel --prod`) upload the local working tree directly and never depend on git tracking. GitHub-integration builds clone from git, so they had never had these files at all, and failed with dozens of simultaneous `Module not found: Can't resolve '@/lib/...'` Turbopack errors, one per component that imported from `lib/`. The fix: anchor the whole Python distribution/packaging block in `.gitignore` with a leading `/` (`/lib/`, `/build/`, `/dist/`, etc.) so it only matches at the repo root, and commit the previously-excluded files. This is the kind of failure class worth knowing about in any monorepo that mixes a Python `.gitignore` template with a JS/TS subproject.

## CORS

`API_CORS_ORIGINS` (`Settings.API_CORS_ORIGINS`, `backend/core/config.py`) defaults to `["http://localhost:3000"]`, matching `next dev`'s default port for local development with no extra configuration needed. In production it's set (as a JSON array, via FastAPI Cloud's environment variable UI) to include the deployed frontend's exact origin:

```
API_CORS_ORIGINS=["http://localhost:3000","https://frontend-naman-213.vercel.app"]
```

The exact origin is required, not a wildcard: `backend/api/app.py` configures `CORSMiddleware` with `allow_credentials=True`, and browsers reject `Access-Control-Allow-Origin: *` on any credentialed request (every authenticated call and the SSE connection's `?token=` query param both count). Verified against the live deployment with real preflight (`OPTIONS`) and actual `GET` requests carrying an `Origin` header matching the deployed frontend.

## Known Gaps

* **No CI.** No `.github/workflows/` exists; both deploys (FastAPI Cloud, Vercel) build directly from a push to `main` with no automated test gate in between. `pytest` and `tsc --noEmit`/`npm run build` are run manually before pushing.
* **No staging environment.** One production deployment per side; there is no separate environment to validate a change against before it reaches `main`.
* **git is non-functional in the FastAPI Cloud environment** (see `GIT_PYTHON_REFRESH=quiet` above) — `GitTool`-backed functionality will not work in production today, only locally and in the Docker image (which does install `git`).
* **No Node.js in the FastAPI Cloud environment either.** FastAPI Cloud builds and runs the source directly via its own Python-only `uv` pipeline, not this repo's Dockerfile — there is no way to install Node.js there. Three of the four `npx`-based MCP servers were reimplemented without a Node dependency because of this (see [MCP_Integration.md](MCP_Integration.md#nodejs-dependency-v17)); `playwright` remains genuinely blocked since real browser automation needs Chromium binaries and Linux system libraries no Python-only environment can provide.
* **Single instance, both sides.** Neither FastAPI Cloud nor Vercel is configured for multiple regions/instances of this app; see [Future_Improvements.md](Future_Improvements.md#api--sse) for the existing single-process SSE/rate-limiting limitation this compounds.
