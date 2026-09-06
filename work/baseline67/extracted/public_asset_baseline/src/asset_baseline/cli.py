from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config, resolve_paths
from .pipeline import generate, inspect, package, prepare, run_all, validate


def _config(args: argparse.Namespace) -> dict:
    return resolve_paths(load_config(Path(args.config), args.set or []), Path(args.config))


def main() -> None:
    parser = argparse.ArgumentParser(description="Zero-history raw-video embodied-asset baseline")
    parser.add_argument("--config", default="config/default.yaml", help="YAML configuration")
    parser.add_argument("--set", action="append", default=[], help="strict dotted configuration override, e.g. reconstruction.backend=primitive")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "prepare", "generate", "package", "validate", "run"):
        subparsers.add_parser(command)
    args = parser.parse_args()
    config = _config(args)
    if args.command == "inspect":
        result = inspect(config)
    elif args.command == "prepare":
        result = {"run_root": str(prepare(config))}
    elif args.command == "generate":
        result = {"run_root": str(generate(config))}
    elif args.command == "package":
        result = {"package": str(package(config))}
    elif args.command == "validate":
        result = validate(config)
    else:
        result = run_all(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
