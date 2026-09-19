
from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

SOURCE_ROOT = REPOSITORY_ROOT / "backend"

WORKSPACE_ROOT = REPOSITORY_ROOT / "workspace"

WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

RUNS_ROOT = REPOSITORY_ROOT / ".agentforge" / "runs"

RUNS_ROOT.mkdir(parents=True, exist_ok=True)
