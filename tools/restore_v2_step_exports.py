"""Restore exact exported STEP bytes and verify recorded SHA256. No CAD edits."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]


def safe(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("STEP paths must stay inside this project")
    return path


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true", help="Verify compressed bytes without writing STEP files")
    parser.add_argument("--force", action="store_true", help="Replace an existing STEP whose hash differs")
    args = parser.parse_args()
    data = json.loads((ROOT / "docs/step_transport.json").read_text(encoding="utf-8"))
    results = []
    for item in data["files"]:
        zipped, original = safe(item["transport_path"]), safe(item["original_path"])
        if digest(zipped) != item["gzip_sha256"]:
            raise ValueError("Compressed SHA256 mismatch: " + item["transport_path"])
        with gzip.open(zipped, "rb") as stream:
            decoded_sha = hashlib.file_digest(stream, "sha256").hexdigest()
        if decoded_sha != item["original_sha256"]:
            raise ValueError("Decoded SHA256 mismatch: " + item["original_path"])
        action = "compressed_verified"
        if not args.verify_only:
            if original.exists() and digest(original) == decoded_sha:
                action = "existing_original_verified"
            else:
                if original.exists() and not args.force:
                    raise ValueError("Existing STEP differs; preserve it or use --force: " + item["original_path"])
                original.parent.mkdir(parents=True, exist_ok=True)
                temporary = original.with_name(original.name + ".restore.tmp")
                with gzip.open(zipped, "rb") as source, temporary.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                if digest(temporary) != decoded_sha:
                    raise ValueError("Written STEP SHA256 mismatch: " + str(temporary))
                temporary.replace(original)
                action = "restored_and_verified"
        results.append({"path": item["original_path"], "sha256": decoded_sha, "action": action})
    print(json.dumps({"ok": True, "files": results}, indent=2))


if __name__ == "__main__":
    main()
