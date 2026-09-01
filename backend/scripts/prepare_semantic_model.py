"""Download and verify the immutable offline semantic model used in production."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

MODEL_ID = "intfloat/multilingual-e5-small"
PINNED_REVISION = "8d923955b027282ba975c0a4c825486c9ca4c490"
PINNED_WEIGHTS_SHA256 = "1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477"
REQUIRED_FILES = {
    "model.safetensors", "config.json", "modules.json", "sentence_bert_config.json",
    "sentencepiece.bpe.model", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
    "1_Pooling/config.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(destination: Path, revision: str) -> None:
    if revision != PINNED_REVISION:
        raise ValueError("Semantic model revision is not approved")
    missing = sorted(name for name in REQUIRED_FILES if not (destination / name).is_file())
    if missing:
        raise ValueError(f"Semantic model files missing: {missing}")
    actual = sha256(destination / "model.safetensors")
    if actual != PINNED_WEIGHTS_SHA256:
        raise ValueError("Semantic model weights checksum mismatch")
    manifest = {"model_id": MODEL_ID, "revision": revision, "weights_sha256": actual}
    (destination / "fincontract-model-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("download", "verify"))
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--revision", default=PINNED_REVISION)
    args = parser.parse_args()
    if args.action == "download":
        from huggingface_hub import snapshot_download
        snapshot_download(
            MODEL_ID, revision=args.revision, local_dir=args.destination,
            allow_patterns=sorted(REQUIRED_FILES),
        )
    verify(args.destination, args.revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
