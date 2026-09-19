
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from backend.state.repository_snapshot import RepositorySnapshot
from backend.state.test_plan import TestPlan, TestStage

logger = logging.getLogger(__name__)

_PYTHON_MANIFESTS = ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile")
_NODE_MANIFEST = "package.json"

_PYTEST_TEST_FILE = re.compile(r"(^|/)(test_[\w]+\.py|[\w]+_test\.py)$")
_JS_TEST_FILE = re.compile(
    r"(^|/)(__tests__/.+|.+\.(test|spec)\.(js|jsx|ts|tsx))$"
)
_IGNORED_DIR_PARTS = {
    ".git", ".venv", "venv", "node_modules", "dist", "build",
    "coverage", "__pycache__", ".next", ".staging",
}


class TestDiscoveryError(Exception):

    __test__ = False


class TestDiscoveryService:
    __test__ = False

    def discover(self, snapshot: RepositorySnapshot) -> list[TestPlan]:

        root = Path(snapshot.project_root)
        file_set = set(snapshot.file_tree)

        sub_roots = self._candidate_sub_roots(snapshot.file_tree)

        plans: list[TestPlan] = []

        other_roots = [r for r in sub_roots if r != "."]

        root_has_manifest = (
            self._find_manifest(file_set, ".", _PYTHON_MANIFESTS) is not None
            or self._find_manifest(file_set, ".", (_NODE_MANIFEST,)) is not None
        )

        for sub_root in sub_roots:
            python_manifest = self._find_manifest(file_set, sub_root, _PYTHON_MANIFESTS)
            node_manifest = self._find_manifest(file_set, sub_root, (_NODE_MANIFEST,))

            own_files = [
                f for f in snapshot.file_tree
                if self._under(f, sub_root)
                and (sub_root != "." or not any(self._under(f, other) for other in other_roots))
            ]

            fallback_eligible = python_manifest is None and node_manifest is None and (
                sub_root == "." or not root_has_manifest
            )
            has_python_files = fallback_eligible and any(f.endswith(".py") for f in own_files)
            has_js_files = fallback_eligible and any(
                Path(f).suffix in {".js", ".jsx", ".ts", ".tsx"} for f in own_files
            )

            if python_manifest is not None or (node_manifest is None and has_python_files):
                plans.append(
                    self._build_python_plan(
                        root=root,
                        sub_root=sub_root,
                        manifest=python_manifest,
                        file_tree=snapshot.file_tree,
                    )
                )
            elif node_manifest is not None or has_js_files:
                plans.append(
                    self._build_node_plan(
                        root=root,
                        sub_root=sub_root,
                        manifest=node_manifest,
                        file_tree=snapshot.file_tree,
                    )
                )

        return plans


    @staticmethod
    def _candidate_sub_roots(file_tree: list[str]) -> list[str]:

        roots = {"."}

        for path in file_tree:
            parts = path.split("/")
            if len(parts) > 1 and parts[0] not in _IGNORED_DIR_PARTS:
                roots.add(parts[0])

        return sorted(roots)

    @staticmethod
    def _find_manifest(file_set: set[str], sub_root: str, names: tuple[str, ...]) -> str | None:
        for name in names:
            candidate = name if sub_root == "." else f"{sub_root}/{name}"
            if candidate in file_set:
                return candidate
        return None


    def _build_python_plan(
        self,
        *,
        root: Path,
        sub_root: str,
        manifest: str | None,
        file_tree: list[str],
    ) -> TestPlan:
        test_files = [
            path for path in file_tree
            if self._under(path, sub_root) and _PYTEST_TEST_FILE.search(path)
        ]

        config_files = [
            path for path in file_tree
            if self._under(path, sub_root)
            and Path(path).name in {"pytest.ini", "pyproject.toml", "setup.cfg", "conftest.py"}
        ]

        uses_pytest = self._python_declares_pytest(root, manifest, config_files)
        package_manager = "pip" if manifest else None

        working_directory = sub_root

        if not test_files:
            return TestPlan(
                framework="none",
                runtime="python",
                working_directory=working_directory,
                stages=[
                    TestStage(name="compile_check", command=["python", "-m", "compileall", "."]),
                ],
                targeted_test_capability=False,
                test_files=[],
                configuration_files=config_files,
                dependency_manifest=manifest,
                package_manager=package_manager,
            )

        framework = "pytest" if uses_pytest else "unittest"
        command = ["python", "-m", "pytest"] if framework == "pytest" else ["python", "-m", "unittest"]

        return TestPlan(
            framework=framework,
            runtime="python",
            working_directory=working_directory,
            stages=[TestStage(name="full_suite", command=command)],
            targeted_test_capability=framework == "pytest",
            test_files=test_files,
            configuration_files=config_files,
            dependency_manifest=manifest,
            package_manager=package_manager,
        )

    @staticmethod
    def _python_declares_pytest(root: Path, manifest: str | None, config_files: list[str]) -> bool:
        if any(Path(f).name == "pytest.ini" for f in config_files):
            return True

        if manifest is None:
            return True

        try:
            manifest_text = (root / manifest).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return True

        lowered = manifest_text.lower()
        if "unittest" in lowered and "pytest" not in lowered:
            return False

        return True


    def _build_node_plan(
        self,
        *,
        root: Path,
        sub_root: str,
        manifest: str | None,
        file_tree: list[str],
    ) -> TestPlan:
        test_files = [
            path for path in file_tree
            if self._under(path, sub_root) and _JS_TEST_FILE.search(path)
        ]

        config_files = [
            path for path in file_tree
            if self._under(path, sub_root)
            and Path(path).name in {
                "jest.config.js", "jest.config.ts", "jest.config.mjs",
                "vitest.config.js", "vitest.config.ts",
            }
        ]

        package_json = self._read_package_json(root, manifest) if manifest else None
        package_manager = "npm" if manifest else None
        working_directory = sub_root

        test_script = (package_json.get("scripts") or {}).get("test") if package_json else None
        has_real_test_script = bool(test_script) and "no test specified" not in test_script

        deps = {
            **(package_json.get("dependencies") or {}),
            **(package_json.get("devDependencies") or {}),
        } if package_json else {}

        if has_real_test_script:
            return TestPlan(
                framework="npm-script",
                runtime="node",
                working_directory=working_directory,
                stages=[TestStage(name="full_suite", command=["npm", "test"])],
                targeted_test_capability=False,
                test_files=test_files,
                configuration_files=config_files,
                dependency_manifest=manifest,
                package_manager=package_manager,
            )

        if "vitest" in deps:
            return TestPlan(
                framework="vitest",
                runtime="node",
                working_directory=working_directory,
                stages=[TestStage(name="full_suite", command=["npx", "vitest", "run"])],
                targeted_test_capability=True,
                test_files=test_files,
                configuration_files=config_files,
                dependency_manifest=manifest,
                package_manager=package_manager,
            )

        if "jest" in deps or test_files:
            return TestPlan(
                framework="jest",
                runtime="node",
                working_directory=working_directory,
                stages=[TestStage(name="full_suite", command=["npx", "jest"])],
                targeted_test_capability=True,
                test_files=test_files,
                configuration_files=config_files,
                dependency_manifest=manifest,
                package_manager=package_manager,
            )

        has_build_script = bool((package_json.get("scripts") or {}).get("build")) if package_json else False

        return TestPlan(
            framework="none",
            runtime="node",
            working_directory=working_directory,
            stages=(
                [TestStage(name="build_check", command=["npm", "run", "build"])]
                if has_build_script
                else []
            ),
            targeted_test_capability=False,
            test_files=[],
            configuration_files=config_files,
            dependency_manifest=manifest,
            package_manager=package_manager,
        )

    @staticmethod
    def _read_package_json(root: Path, manifest: str) -> dict | None:
        try:
            text = (root / manifest).read_text(encoding="utf-8", errors="ignore")
            return json.loads(text)
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not parse %s; falling back to file-based Node test detection.", manifest)
            return None

    @staticmethod
    def _under(path: str, sub_root: str) -> bool:
        if sub_root == ".":
            return True
        return path == sub_root or path.startswith(f"{sub_root}/")
