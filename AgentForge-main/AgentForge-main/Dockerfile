# syntax=docker/dockerfile:1

# AgentForge backend (FastAPI + LangGraph + MCP) -- production image.
# Backend only: the Next.js frontend is not built or served by this image.

# ---- Stage 1: build Python dependencies ------------------------------------
FROM python:3.11-slim AS deps

WORKDIR /app

# build-essential covers any transitive dependency without a prebuilt wheel
# for the target platform; it does not ship in the final image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Node.js/npm, copied directly from the official image rather than
# `apt-get install nodejs npm`: Debian's packaged npm pulls in an unrelated
# build toolchain (webpack, babel, jest, node-gyp, ~190s and hundreds of MB)
# as transitive package dependencies. Required for npx-based MCP servers
# (playwright, filesystem, postgres, sequential-thinking) and for
# testing/building generated Node.js/React projects (TestDiscoveryService's
# node plan runs `npm test` / `npm run build` inside generated repos).
FROM node:20-bookworm-slim AS node


# ---- Stage 3: runtime --------------------------------------------------------
FROM python:3.11-slim AS runtime

# git             -- required by GitTool (GitPython shells out to the git binary).
# ca-certificates -- outbound HTTPS to LLM providers and HTTP-transport MCP servers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

COPY --from=deps /install /usr/local

WORKDIR /app

COPY backend/ backend/
COPY alembic/ alembic/
COPY alembic.ini .

# Runtime directories AgentForge writes to (workspace output, run state,
# app logs). backend/core/workspace.py and backend/core/logging.py also
# create these on import; creating them here fixes ownership up front.
RUN mkdir -p workspace .agentforge/runs logs \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app

USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

# Lightweight: /health does not hit any external dependency, only reports
# already-established application/DB state.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=3)" || exit 1

# `exec` replaces the shell so uvicorn is PID 1 and receives SIGTERM directly,
# letting the FastAPI lifespan's shutdown (MCP client close_all, DB engine
# dispose, tracing shutdown) run instead of being killed outright.
CMD ["sh", "-c", "exec python -m uvicorn backend.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
