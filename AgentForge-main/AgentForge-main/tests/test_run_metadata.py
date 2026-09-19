from __future__ import annotations

from datetime import UTC, datetime

from backend.state.run_metadata import RUN_METADATA_SCHEMA_VERSION, RunMetadata


def test_run_metadata_requires_run_id() -> None:
    metadata = RunMetadata(run_id="af_20260713_deadbeef")

    assert metadata.run_id == "af_20260713_deadbeef"
    assert metadata.schema_version == RUN_METADATA_SCHEMA_VERSION
    assert metadata.created_at.tzinfo is not None
    assert metadata.updated_at.tzinfo is not None


def test_run_metadata_round_trips_through_json() -> None:
    original = RunMetadata(run_id="af_20260713_deadbeef")

    restored = RunMetadata.model_validate_json(original.model_dump_json())

    assert restored == original


def test_run_metadata_updated_at_can_be_advanced() -> None:
    metadata = RunMetadata(run_id="af_20260713_deadbeef")
    later = datetime.now(UTC)

    metadata.updated_at = later

    assert metadata.updated_at == later
