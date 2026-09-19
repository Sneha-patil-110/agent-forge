
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )

    try:
        with os.fdopen(fd, "w", encoding=encoding) as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())

        os.replace(tmp_name, path)

    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
