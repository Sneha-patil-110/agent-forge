#!/usr/bin/env python3
"""Tiny local server that tails a real AgentForge CLI run's log file and
exposes it as JSON, plus serves the static live-dashboard page. No database,
no auth -- just watches the actual run happening on this machine."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/demo_run_calc.log")
STATIC_DIR = Path(__file__).resolve().parent

_run_lock = threading.Lock()
_current_process: subprocess.Popen | None = None


def start_new_run(prompt: str) -> tuple[bool, str]:
    global _current_process

    with _run_lock:
        if _current_process is not None and _current_process.poll() is None:
            return False, "A run is already in progress."

        shutil.rmtree(REPO_ROOT / ".agentforge", ignore_errors=True)
        shutil.rmtree(REPO_ROOT / "workspace", ignore_errors=True)

        log_fh = LOG_FILE.open("w")
        venv_python = REPO_ROOT / "venv" / "bin" / "python3"
        _current_process = subprocess.Popen(
            [str(venv_python), "-m", "backend.cli.main", "create", prompt],
            cwd=str(REPO_ROOT),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )
        return True, "started"

AGENT_ORDER = [
    "analysis", "planner", "architect", "developer",
    "tester", "debugger", "reviewer", "documentation",
]

PROVIDER_BY_ROLE: dict[str, dict[str, str]] = {}
try:
    import yaml
    cfg = yaml.safe_load((REPO_ROOT / "backend/llms/config/models.yaml").read_text())
    for role, c in cfg.items():
        PROVIDER_BY_ROLE[role] = {"provider": c.get("provider", "-"), "model": c.get("model", "-")}
except Exception:
    pass

START_RE = re.compile(r"(?P<ts>[\d-]{10} [\d:]{8}) \| INFO .*\| (?P<agent>\w+) agent started")
DONE_RE = re.compile(r"(?P<ts>[\d-]{10} [\d:]{8}) \| INFO .*\| (?P<agent>\w+) agent completed")
FAIL_RE = re.compile(r"(?P<ts>[\d-]{10} [\d:]{8}) \| ERROR .*\| (?P<agent>\w+) agent failed: (?P<msg>.*)")
HTTP_RE = re.compile(r"(?P<ts>[\d-]{10} [\d:]{8}) \| INFO .*\| httpx \| HTTP Request: POST https://(?P<host>[^/]+)\S* \"HTTP/1\.1 (?P<code>\d+)")
MATERIALIZED_RE = re.compile(r"(?P<ts>[\d-]{10} [\d:]{8}) \| INFO .*\| Materialized (?P<n>\d+) of (?P<m>\d+) file\(s\) to (?P<path>\S+)")
DEP_RETRY_RE = re.compile(r"(?P<ts>[\d-]{10} [\d:]{8}) \| WARNING .*dependency_preparation_service \| Dependency installation hit a transient failure \(attempt (?P<n>\d+)/(?P<m>\d+)\): (?P<msg>.*)")
INFRA_FAIL_RE = re.compile(r"(?P<ts>[\d-]{10} [\d:]{8}) \| ERROR .*\| (?P<msg>Test infrastructure failure.*)")
WORKFLOW_DONE_RE = re.compile(r"Status: (?P<status>\S+)")
RUN_ID_RE = re.compile(r"run=(?P<run_id>af_\d+_[0-9a-f]+)")


def load_run_outputs(run_id: str) -> dict:
    """Real per-stage agent output, straight from the run's persisted state
    -- the actual planning/architecture reasoning, not just final files."""
    state_path = REPO_ROOT / ".agentforge" / "runs" / run_id / "state.json"

    if not state_path.exists():
        return {}

    try:
        state = json.loads(state_path.read_text())
    except Exception:
        return {}

    outputs: dict[str, dict] = {}

    project = state.get("project") or {}
    if project.get("objective"):
        outputs["analysis"] = {
            "objective": project.get("objective"),
            "requirements": project.get("requirements"),
            "tech_stack": project.get("tech_stack"),
        }

    planning = state.get("planning") or {}
    if planning.get("project_summary"):
        outputs["planner"] = {
            "summary": planning.get("project_summary"),
            "strategy": planning.get("implementation_strategy"),
            "tasks": [t.get("title") for t in (planning.get("tasks") or [])],
        }

    architecture = state.get("architecture") or {}
    if architecture.get("architecture_summary"):
        outputs["architect"] = {
            "summary": architecture.get("architecture_summary"),
            "layers": [
                layer.get("name")
                for layer in (architecture.get("system_design") or {}).get("layers", [])
            ],
        }

    testing = state.get("testing") or {}
    if testing.get("testing_summary"):
        outputs["tester"] = {
            "summary": testing.get("testing_summary"),
            "passed": testing.get("passed"),
            "tests": f"{testing.get('passed_tests', 0)} passed / {testing.get('failed_tests', 0)} failed",
        }

    review = state.get("review") or {}
    if review.get("review_summary"):
        outputs["reviewer"] = {
            "summary": review.get("review_summary"),
            "passed": review.get("passed") or review.get("auto_passed"),
            "score": review.get("score"),
        }

    documentation = state.get("documentation") or {}
    if documentation.get("documentation_summary"):
        outputs["documentation"] = {"summary": documentation.get("documentation_summary")}

    return outputs


def host_to_provider(host: str) -> str:
    if "groq" in host:
        return "groq"
    if "googleapis" in host:
        return "google"
    if "openrouter" in host:
        return "openrouter"
    if "nvidia" in host:
        return "nvidia"
    if "cloudflare" in host:
        return "cloudflare"
    return host


def parse_log(text: str) -> dict:
    agents: dict[str, dict] = {
        role: {"role": role, "status": "pending", **PROVIDER_BY_ROLE.get(role, {})}
        for role in AGENT_ORDER
    }
    http_calls: list[dict] = []
    events: list[dict] = []
    materialized: dict | None = None
    dep_retries: list[dict] = []
    infra_failure: str | None = None
    final_status: str | None = None
    run_id: str | None = None

    for line in text.splitlines():
        m = RUN_ID_RE.search(line)
        if m:
            run_id = m["run_id"]

        m = START_RE.search(line)
        if m and m["agent"] in agents:
            agents[m["agent"]]["status"] = "running"
            agents[m["agent"]]["started_at"] = m["ts"]
            events.append({"ts": m["ts"], "text": f"{m['agent']} agent started"})
            continue

        m = DONE_RE.search(line)
        if m and m["agent"] in agents:
            agents[m["agent"]]["status"] = "completed"
            agents[m["agent"]]["completed_at"] = m["ts"]
            events.append({"ts": m["ts"], "text": f"{m['agent']} agent completed"})
            continue

        m = FAIL_RE.search(line)
        if m and m["agent"] in agents:
            agents[m["agent"]]["status"] = "failed"
            agents[m["agent"]]["error"] = m["msg"]
            events.append({"ts": m["ts"], "text": f"{m['agent']} agent failed"})
            continue

        m = HTTP_RE.search(line)
        if m:
            http_calls.append({"ts": m["ts"], "provider": host_to_provider(m["host"]), "code": m["code"]})
            continue

        m = MATERIALIZED_RE.search(line)
        if m:
            materialized = {"ts": m["ts"], "n": int(m["n"]), "m": int(m["m"]), "path": m["path"]}
            events.append({"ts": m["ts"], "text": f"Materialized {m['n']}/{m['m']} files"})
            continue

        m = DEP_RETRY_RE.search(line)
        if m:
            dep_retries.append({"ts": m["ts"], "attempt": int(m["n"]), "max": int(m["m"]), "msg": m["msg"]})
            events.append({"ts": m["ts"], "text": f"Dependency install retry {m['n']}/{m['m']}"})
            continue

        m = INFRA_FAIL_RE.search(line)
        if m:
            infra_failure = m["msg"]
            events.append({"ts": m["ts"], "text": "Test infrastructure failure"})
            continue

        m = WORKFLOW_DONE_RE.search(line)
        if m:
            final_status = m["status"]

    generated_files = []
    if materialized:
        proj_dir = Path(materialized["path"])
        if proj_dir.exists():
            for p in sorted(proj_dir.rglob("*")):
                if p.is_file() and ".venv" not in p.parts and ".git" not in p.parts:
                    try:
                        content = p.read_text(errors="replace")
                    except Exception:
                        content = "<binary file>"
                    generated_files.append({
                        "path": str(p.relative_to(proj_dir)),
                        "content": content[:8000],
                    })

    run_outputs = load_run_outputs(run_id) if run_id else {}
    for role, output in run_outputs.items():
        if role in agents:
            agents[role]["output"] = output

    return {
        "agents": [agents[role] for role in AGENT_ORDER],
        "http_calls": http_calls,
        "events": events,
        "materialized": materialized,
        "dependency_retries": dep_retries,
        "infra_failure": infra_failure,
        "final_status": final_status,
        "generated_files": generated_files,
        "log_lines": len(text.splitlines()),
        "run_id": run_id,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/status"):
            text = LOG_FILE.read_text(errors="replace") if LOG_FILE.exists() else ""
            self._send_json(parse_log(text))
            return

        # static file serving
        rel = self.path.lstrip("/") or "index.html"
        file_path = STATIC_DIR / rel
        if not file_path.exists() or not file_path.is_file():
            file_path = STATIC_DIR / "index.html"

        content_type = "text/html"
        if file_path.suffix == ".js":
            content_type = "application/javascript"
        elif file_path.suffix == ".css":
            content_type = "text/css"

        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path.startswith("/api/start"):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                payload = {}
            prompt = (payload.get("prompt") or "").strip()

            if not prompt:
                self._send_json({"ok": False, "error": "Prompt is empty."}, 400)
                return

            ok, msg = start_new_run(prompt)
            self._send_json({"ok": ok, "error": None if ok else msg})
            return

        self._send_json({"ok": False, "error": "Unknown endpoint."}, 404)


if __name__ == "__main__":
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 4141
    print(f"Watching {LOG_FILE} -- serving on http://0.0.0.0:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
