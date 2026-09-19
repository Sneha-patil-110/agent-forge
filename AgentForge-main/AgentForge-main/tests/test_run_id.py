from __future__ import annotations

import re

import pytest

from backend.core.exceptions import InvalidRunIdError
from backend.utils.run_id import RUN_ID_PATTERN, generate_run_id, validate_run_id


def test_generate_run_id_matches_pattern() -> None:
    run_id = generate_run_id()

    assert RUN_ID_PATTERN.fullmatch(run_id)
    assert re.fullmatch(r"af_\d{8}_[0-9a-f]{8}", run_id)


def test_generate_run_id_is_unique_across_many_calls() -> None:
    run_ids = {generate_run_id() for _ in range(500)}

    assert len(run_ids) == 500


def test_validate_run_id_accepts_valid_id() -> None:
    run_id = generate_run_id()

    assert validate_run_id(run_id) == run_id


@pytest.mark.parametrize(
    "bad_run_id",
    [
        "../backend",
        "../../secrets",
        "/etc/passwd",
        r"C:\Users\something",
        "af_test/../../../backend",
        "af_20260713_ZZZZZZZZ",
        "af_20260713_short",
        "not_a_run_id",
        "",
        "af_20260713_deadbeef ",
        "af_20260713_DEADBEEF",
    ],
)
def test_validate_run_id_rejects_unsafe_or_malformed_ids(bad_run_id: str) -> None:
    with pytest.raises(InvalidRunIdError):
        validate_run_id(bad_run_id)


def test_validate_run_id_rejects_non_string() -> None:
    with pytest.raises(InvalidRunIdError):
        validate_run_id(12345)
