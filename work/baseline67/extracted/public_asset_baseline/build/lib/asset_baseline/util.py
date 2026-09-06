from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ.setdefault("PYTHONHASHSEED", str(seed))


def ensure_new_dir(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing run directory: {path}")
    path.mkdir(parents=True)


def clean_dir(path: Path) -> None:
    """Create an output directory; it must be absent or an empty directory."""
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def iter_files(root: Path) -> Iterable[Path]:
    yield from sorted(path for path in root.rglob("*") if path.is_file() and not path.name.startswith("._"))
