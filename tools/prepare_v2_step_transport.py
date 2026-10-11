"""Lossless deterministic gzip copies of final STEP exports; keep originals."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
BOARD_PATHS = [
    "output/POWER/MeshRepeater2_Power.step",
    "output/LOGIC/MeshRepeater2_Logic.step",
]
ASSEMBLY_PATHS = [
    "docs/mechanics/MeshRepeater2_assembly.step",
    "docs/mechanics/MeshRepeater2_exploded.step",
]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-assembly", action="store_true",
                        help="Use only after the final mechanical exports are complete")
    args = parser.parse_args()
    manifest = ROOT / "docs/step_transport.json"
    old = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {"files": []}
    rows = {row["original_path"]: row for row in old["files"]}
    paths = BOARD_PATHS + (ASSEMBLY_PATHS if args.include_assembly else [])
    for relative in paths:
        source = ROOT / relative
        with source.open("rb") as stream:
            assert stream.read(32).lstrip().startswith(b"ISO-10303-21;"), relative
        source_sha = digest(source)
        zipped = source.with_suffix(source.suffix + ".gz")
        temporary = zipped.with_name(zipped.name + ".tmp")
        with source.open("rb") as original, temporary.open("wb") as target:
            with gzip.GzipFile(filename="", mode="wb", fileobj=target,
                               compresslevel=9, mtime=0) as packed:
                shutil.copyfileobj(original, packed, length=1024 * 1024)
        with gzip.open(temporary, "rb") as decoded:
            recovered_sha = hashlib.file_digest(decoded, "sha256").hexdigest()
        assert recovered_sha == source_sha and digest(source) == source_sha, relative
        temporary.replace(zipped)
        rows[relative] = {
            "original_path": relative,
            "transport_path": zipped.relative_to(ROOT).as_posix(),
            "original_size_bytes": source.stat().st_size,
            "original_sha256": source_sha,
            "gzip_size_bytes": zipped.stat().st_size,
            "gzip_sha256": digest(zipped),
            "verified_decompressed_sha256": recovered_sha,
        }
    output = {
        "format": "Mesh Repeater 2.0 lossless STEP gzip transport v1",
        "compression": "gzip, level9, empty header filename, mtime0",
        "scope": "Exported large ASCII STEP only. Native KiCad 3D libraries remain uncompressed.",
        "original_exports_manifests_modified": False,
        "restore_command": "python tools/restore_v2_step_exports.py",
        "files": [rows[name] for name in sorted(rows)],
    }
    manifest.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(output["files"]), "manifest": "docs/step_transport.json",
                      "copies": [{"path": rows[name]["transport_path"],
                                  "size": rows[name]["gzip_size_bytes"]} for name in paths]}))


if __name__ == "__main__":
    main()
