#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from app.vectorstore.manifest import validate_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--schema", type=Path, default=Path("../research/manifest.schema.json"))
    args = parser.parse_args()
    manifest = validate_manifest(args.manifest, args.schema)
    print(f"manifest {manifest['manifest_version']}: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
