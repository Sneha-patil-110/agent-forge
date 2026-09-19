
from __future__ import annotations

from backend.services.pip_failure_classifier import (
    PipFailureKind,
    classify_pip_failure,
    summarize_pip_failure,
)

REAL_INCIDENT_STDOUT = (
    "Defaulting to user installation because normal site-packages is not writeable\n"
    "Collecting fastapi==0.109.0 (from -r requirements.txt (line 1))\n"
    "  Downloading fastapi-0.109.0-py3-none-any.whl.metadata (24 kB)\n"
    "Collecting psycopg2-binary==2.9.9 (from -r requirements.txt (line 4))\n"
    "  Downloading psycopg2-binary-2.9.9.tar.gz (384 kB)\n"
    "  Installing build dependencies: started\n"
    "  Installing build dependencies: finished with status 'done'\n"
)
REAL_INCIDENT_STDERR = (
    "  error: subprocess-exited-with-error\n"
    "  \n"
    "  Building wheel for psycopg2-binary (pyproject.toml) did not run successfully.\n"
    "  exit code: 1\n"
    "  \n"
    "  [115 lines of output]\n"
    "  running build_ext\n"
    "  building 'psycopg2._psycopg' extension\n"
    "  fatal error C1083: Cannot open include file: 'libpq-fe.h': No such file or directory\n"
)


REAL_PYDANTIC_CORE_STDOUT = (
    "Collecting pydantic-core==2.14.6 (from pydantic==2.5.3->-r requirements.txt (line 1))\n"
    "  Using cached pydantic_core-2.14.6.tar.gz (360 kB)\n"
    "  Installing build dependencies: started\n"
    "  Installing build dependencies: finished with status 'done'\n"
    "Building wheels for collected packages: pydantic-core\n"
    "  Building wheel for pydantic-core (pyproject.toml): started\n"
    "  Building wheel for pydantic-core (pyproject.toml): finished with status 'error'\n"
    "Failed to build pydantic-core\n"
)
REAL_PYDANTIC_CORE_STDERR = (
    "  error: failed to run custom build command for `pydantic-core v2.14.6`\n"
    "  \U0001f4a5 maturin failed\n"
    "  ERROR: Failed building wheel for pydantic-core\n"
    "error: failed-wheel-build-for-install\n"
)


def test_real_incident_output_classifies_as_python_incompatible() -> None:
    kind = classify_pip_failure(stdout=REAL_INCIDENT_STDOUT, stderr=REAL_INCIDENT_STDERR)

    assert kind == PipFailureKind.PYTHON_INCOMPATIBLE


def test_real_pydantic_core_output_classifies_as_python_incompatible() -> None:

    kind = classify_pip_failure(stdout=REAL_PYDANTIC_CORE_STDOUT, stderr=REAL_PYDANTIC_CORE_STDERR)

    assert kind == PipFailureKind.PYTHON_INCOMPATIBLE


def test_pip_explicit_requires_different_python_message() -> None:
    stderr = (
        "ERROR: Package 'somepkg' requires a different Python: 3.13.1 not in '<3.12'\n"
    )

    kind = classify_pip_failure(stdout="", stderr=stderr)

    assert kind == PipFailureKind.PYTHON_INCOMPATIBLE


def test_bad_version_is_dependency_error() -> None:
    stderr = (
        "ERROR: Could not find a version that satisfies the requirement "
        "somepkg==99.99.99 (from versions: 1.0.0, 1.0.1)\n"
        "ERROR: No matching distribution found for somepkg==99.99.99\n"
    )

    kind = classify_pip_failure(stdout="", stderr=stderr)

    assert kind == PipFailureKind.DEPENDENCY_ERROR


def test_nonexistent_package_is_dependency_error() -> None:
    stderr = "ERROR: No matching distribution found for this-package-definitely-does-not-exist-ever-12345\n"

    kind = classify_pip_failure(stdout="", stderr=stderr)

    assert kind == PipFailureKind.DEPENDENCY_ERROR


def test_resolution_conflict_is_dependency_error() -> None:
    stderr = (
        "ERROR: Cannot install a==1.0.0 and b==2.0.0 because these package versions "
        "have conflicting dependencies.\n"
        "ERROR: ResolutionImpossible: for help visit ...\n"
    )

    kind = classify_pip_failure(stdout="", stderr=stderr)

    assert kind == PipFailureKind.DEPENDENCY_ERROR


def test_network_timeout_is_transient() -> None:
    stderr = (
        "pip._vendor.urllib3.exceptions.ReadTimeoutError: "
        "HTTPSConnectionPool(host='pypi.org', port=443): Read timed out.\n"
    )

    kind = classify_pip_failure(stdout="", stderr=stderr)

    assert kind == PipFailureKind.TRANSIENT


def test_dns_failure_is_transient() -> None:
    stderr = "Temporary failure in name resolution\n"

    kind = classify_pip_failure(stdout="", stderr=stderr)

    assert kind == PipFailureKind.TRANSIENT


def test_permission_denied_is_transient() -> None:
    stderr = "PermissionError: [Errno 13] Permission denied: 'C:\\\\some\\\\path'\n"

    kind = classify_pip_failure(stdout="", stderr=stderr)

    assert kind == PipFailureKind.TRANSIENT


def test_disk_full_is_transient() -> None:
    stderr = "OSError: [Errno 28] No space left on device\n"

    kind = classify_pip_failure(stdout="", stderr=stderr)

    assert kind == PipFailureKind.TRANSIENT


def test_summarize_extracts_real_pip_error_lines_not_just_exit_code() -> None:
    summary = summarize_pip_failure(
        stdout="",
        stderr=(
            "some noise\n"
            "ERROR: Could not find a version that satisfies the requirement badpkg==9.9.9\n"
            "ERROR: No matching distribution found for badpkg==9.9.9\n"
        ),
    )

    assert "badpkg==9.9.9" in summary
    assert "No matching distribution" in summary


def test_summarize_falls_back_to_last_output_line_when_no_pip_error_line() -> None:
    summary = summarize_pip_failure(
        stdout=REAL_INCIDENT_STDOUT,
        stderr=REAL_INCIDENT_STDERR,
    )

    assert "libpq-fe.h" in summary
