from __future__ import annotations

from pathlib import Path

import pytest

from backend.utils.atomic_io import atomic_write_text


def test_atomic_write_text_creates_file_with_exact_content(tmp_path: Path) -> None:
    target = tmp_path / "state.json"

    atomic_write_text(target, '{"a": 1}')

    assert target.read_text(encoding="utf-8") == '{"a": 1}'


def test_atomic_write_text_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "state.json"

    atomic_write_text(target, "content")

    assert target.read_text(encoding="utf-8") == "content"


def test_atomic_write_text_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    target = tmp_path / "state.json"

    atomic_write_text(target, "content")

    entries = list(tmp_path.iterdir())
    assert entries == [target]


def test_atomic_write_text_overwrites_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    atomic_write_text(target, "old content")

    atomic_write_text(target, "new content")

    assert target.read_text(encoding="utf-8") == "new content"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_text_preserves_original_on_write_failure(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "state.json"
    atomic_write_text(target, "original content")

    monkeypatch.setattr(
        "backend.utils.atomic_io.os.fsync",
        lambda *_: (_ for _ in ()).throw(OSError("simulated disk failure")),
    )

    with pytest.raises(OSError):
        atomic_write_text(target, "new content that must not land")

    assert target.read_text(encoding="utf-8") == "original content"
    assert list(tmp_path.iterdir()) == [target]
