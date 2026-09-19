from __future__ import annotations

import ast
import re

from pydantic import BaseModel, Field

from backend.state.implementation_state import GeneratedCode

_APIROUTER_ASSIGNMENT = re.compile(r"^\s*\w+\s*=\s*APIRouter\s*\(", re.MULTILINE)
_ABSOLUTE_IMPORT = re.compile(r"^\s*(?:from|import)\s+([\w.]+)")
_RELATIVE_IMPORT = re.compile(r"^\s*from\s+(\.+)(\w[\w.]*)?\s+import\s+([\w, *()]+)")


class StaticValidationIssue(BaseModel):
    file: str
    line: int | None = None
    message: str


class StaticValidationResult(BaseModel):
    issues: list[StaticValidationIssue] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues


class StaticValidationService:

    def validate(self, generated_code: list[GeneratedCode]) -> StaticValidationResult:
        python_files = {item.path: item.content for item in generated_code if item.path.endswith(".py")}

        issues: list[StaticValidationIssue] = []

        for path, content in python_files.items():
            issues.extend(self._check_syntax(path, content))

        issues.extend(self._check_local_imports(python_files))
        issues.extend(self._check_route_registration(python_files))

        return StaticValidationResult(issues=issues)

    @staticmethod
    def _check_syntax(path: str, content: str) -> list[StaticValidationIssue]:
        try:
            ast.parse(content, filename=path)
        except SyntaxError as error:
            return [
                StaticValidationIssue(
                    file=path,
                    line=error.lineno,
                    message=f"Syntax error: {error.msg}",
                )
            ]

        return []

    @staticmethod
    def _local_top_level_packages(python_files: dict[str, str]) -> set[str]:
        packages: set[str] = set()

        for path in python_files:
            parts = path.split("/")

            if len(parts) > 1:
                packages.add(parts[0])

        return packages

    def _check_local_imports(self, python_files: dict[str, str]) -> list[StaticValidationIssue]:
        local_packages = self._local_top_level_packages(python_files)
        known_modules = self._known_module_names(python_files)
        issues: list[StaticValidationIssue] = []

        for path, content in python_files.items():
            for lineno, line in enumerate(content.splitlines(), start=1):
                relative_match = _RELATIVE_IMPORT.match(line)

                if relative_match:
                    target = self._resolve_relative_import(path, relative_match.group(1), relative_match.group(2))

                    if target is not None and target not in known_modules:
                        issues.append(
                            StaticValidationIssue(
                                file=path,
                                line=lineno,
                                message=f"Import of local module '{target}' does not match any generated file.",
                            )
                        )

                    continue

                absolute_match = _ABSOLUTE_IMPORT.match(line)

                if not absolute_match:
                    continue

                module = absolute_match.group(1)
                top_level = module.split(".")[0]

                if top_level not in local_packages:
                    continue

                if module not in known_modules and f"{module}.__init__" not in known_modules:
                    issues.append(
                        StaticValidationIssue(
                            file=path,
                            line=lineno,
                            message=f"Import of local module '{module}' does not match any generated file.",
                        )
                    )

        return issues

    @staticmethod
    def _known_module_names(python_files: dict[str, str]) -> set[str]:
        names: set[str] = set()

        for path in python_files:
            without_ext = path[: -len(".py")] if path.endswith(".py") else path
            dotted = without_ext.replace("/", ".")
            names.add(dotted)

            if dotted.endswith(".__init__"):
                names.add(dotted[: -len(".__init__")])

        return names

    @staticmethod
    def _resolve_relative_import(importing_path: str, dots: str, module: str | None) -> str | None:
        parts = importing_path.split("/")[:-1]
        levels_up = len(dots) - 1

        if levels_up > 0:
            parts = parts[:-levels_up] if levels_up <= len(parts) else []

        if module:
            parts = parts + module.split(".")

        return ".".join(parts) if parts else None

    @staticmethod
    def _check_route_registration(python_files: dict[str, str]) -> list[StaticValidationIssue]:
        defines_router = any(_APIROUTER_ASSIGNMENT.search(content) for content in python_files.values())
        wires_router = any("include_router" in content for content in python_files.values())

        if defines_router and not wires_router:
            return [
                StaticValidationIssue(
                    file="<project>",
                    line=None,
                    message=(
                        "One or more APIRouter instances are defined, but "
                        "include_router(...) is never called anywhere -- no "
                        "route is reachable."
                    ),
                )
            ]

        return []
