from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def load_config(path: Path, overrides: list[str]) -> dict[str, Any]:
    """Load YAML and apply strict dotted `key=value` CLI overrides."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"configuration must be a mapping: {path}")
    config = deepcopy(raw)
    for assignment in overrides:
        if "=" not in assignment:
            raise ValueError(f"override must be key=value: {assignment}")
        dotted, value = assignment.split("=", 1)
        keys = dotted.split(".")
        target: dict[str, Any] = config
        for key in keys[:-1]:
            child = target.get(key)
            if not isinstance(child, dict):
                raise KeyError(f"unknown configuration key: {dotted}")
            target = child
        if keys[-1] not in target:
            raise KeyError(f"unknown configuration key: {dotted}")
        target[keys[-1]] = yaml.safe_load(value)
    return config


def resolve_paths(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    """Resolve input/output paths relative to the working directory, not this repo."""
    result = deepcopy(config)
    base = Path.cwd()
    for key in ("question_zip", "submission_example_zip", "output_root"):
        value = Path(str(result[key]))
        result[key] = str((base / value).resolve() if not value.is_absolute() else value.resolve())
    return result
