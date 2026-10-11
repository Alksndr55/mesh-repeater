"""Bounded public-file reads for the GitHub blob uploader; never credentials."""
from pathlib import Path
import argparse
import base64
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
TEMP = ROOT / ".publication_tmp"


def git_blob(path):
    size = path.stat().st_size
    checksum = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["list", "chunk", "verify", "cache"])
    parser.add_argument("--path")
    parser.add_argument("--sha")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--size", type=int, default=24576)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--stable-only", action="store_true", help="Skip final LOGIC/assembly artifacts while exterior labels are being regenerated")
    args = parser.parse_args()
    cache = TEMP / "uploaded_large.json"
    done = set()
    for name in ("uploaded.json", "uploaded_large.json"):
        item = TEMP / name
        if item.exists():
            done.update(json.loads(item.read_text(encoding="utf-8-sig")))
    if args.action == "cache":
        if not args.sha or len(args.sha) != 40 or any(c not in "0123456789abcdef" for c in args.sha):
            raise ValueError("A confirmed Git blob SHA is required")
        large = set(json.loads(cache.read_text(encoding="utf-8-sig"))) if cache.exists() else set()
        large.add(args.sha)
        cache.write_text(json.dumps(sorted(large)) + "\n", encoding="utf-8")
        print(json.dumps({"cached": args.sha, "total": len(large)}))
        return
    inventory = json.loads((TEMP / "files.json").read_text(encoding="utf-8"))
    if args.action == "list":
        unique = {}
        for row in inventory["files"]:
            if row["size"] > 32000 and not row["known_in_base"] and row["sha"] not in done:
                if args.stable_only and (
                    row["path"].startswith("output/LOGIC/")
                    or row["path"].startswith("docs/mechanics/MeshRepeater2_assembly")
                    or row["path"].startswith("docs/mechanics/MeshRepeater2_exploded")
                    or row["path"] == "design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb"
                    or row["path"] in {"audit/v2_native_boards_final.json", "audit/v2_logic_star_fix.json", "audit/v2_routing_engineering.json", "audit/MeshRepeater2_Logic_footprint_variants.json"}
                ):
                    continue
                if row["path"].endswith(".step") and row["size"] > 10000000:
                    raise ValueError("An uncompressed large exported STEP remains in inventory")
                unique.setdefault(row["sha"], row)
        final = [row for row in unique.values() if not row["path"].startswith("audit/")]
        historical = [row for row in unique.values() if row["path"].startswith("audit/")]
        queue = sorted(final, key=lambda row: row["size"]) + sorted(historical, key=lambda row: row["size"])
        print(json.dumps({"files": queue[:args.limit], "remaining": len(queue)}))
        return
    if not args.path or not args.sha:
        raise ValueError("Inventory path and expected SHA are required")
    entries = [row for row in inventory["files"] if row["path"] == args.path and row["sha"] == args.sha]
    if len(entries) != 1:
        raise ValueError("Requested path/SHA must be in the public inventory")
    path = (ROOT / args.path).resolve()
    if not path.is_relative_to(ROOT) or ".publication_tmp" in path.parts:
        raise ValueError("Only project public files are readable")
    if args.action == "verify":
        actual = git_blob(path)
        print(json.dumps({"ok": actual == args.sha, "sha": actual, "size": path.stat().st_size}))
        return
    if args.size <= 0 or args.size > 49152 or args.offset < 0:
        raise ValueError("Read bounds exceeded")
    if path.stat().st_size != entries[0]["size"]:
        raise ValueError("Public file size changed")
    with path.open("rb") as stream:
        stream.seek(args.offset)
        data = stream.read(args.size)
    print(json.dumps({"content": base64.b64encode(data).decode("ascii"), "bytes": len(data),
                      "offset": args.offset, "eof": args.offset + len(data) >= path.stat().st_size}))


if __name__ == "__main__":
    main()
