#!/usr/bin/env python3
"""Prove native product schematics are projections of the shared v1-led circuit.

Only fresh netlist/ERC exports and this report are written. Native schematics,
models, project settings, PCB tracks, vias, pads and filled zones are read-only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from circuit_io import Union, children, netlist, one, properties, sexpr, sha256, source_files, value


VARIANT_FIELDS = (
    "Value_NaIon", "Value_NaIon_NoCold", "Value_LTO_2S",
    "MPN_NaIon", "MPN_NaIon_NoCold", "MPN_LTO_2S",
    "Fit_NaIon", "Fit_NaIon_NoCold", "Fit_LTO_2S",
)
COMPARED_FIELDS = ("Value", "MPN", "Footprint", *VARIANT_FIELDS)


def cli_path(given: str | None) -> Path:
    candidates = [given, shutil.which("kicad-cli"), "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise FileNotFoundError("KiCad 10 kicad-cli not found; pass --kicad-cli PATH")


def relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path.resolve())


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[2] / "project.json")
    parser.add_argument("--product", action="append", choices=("v1", "v2"), help="Repeat to select products; default both")
    parser.add_argument("--out", type=Path, help="Report/export directory; default an OS temporary directory")
    parser.add_argument("--kicad-cli")
    args = parser.parse_args()
    config_path = args.config.resolve()
    root = config_path.parent
    config = load(config_path)
    profiles_path = root / config["circuit"]["profiles"]
    profiles = load(profiles_path)
    canonical = root / config["circuit"]["schematic"]
    selected = list(dict.fromkeys(args.product or list(config["products"])))
    out = args.out.resolve() if args.out else Path(tempfile.mkdtemp(prefix="mesh-circuit-"))
    out.mkdir(parents=True, exist_ok=True)
    cli = cli_path(args.kicad_cli)
    checks: list[dict] = []
    commands: list[dict] = []
    frozen: dict[Path, str] = {}

    def check(name: str, passed: bool, detail=None) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    def freeze_schematic(path: Path) -> None:
        for file in source_files(path):
            frozen[file] = sha256(file)
        for name in [path.stem + ".kicad_pro", "model.json", "sym-lib-table", "fp-lib-table", "Meshcore.kicad_sym"]:
            file = path.parent / name
            if file.is_file():
                frozen[file] = sha256(file)

    def run(arguments: list[str]) -> subprocess.CompletedProcess:
        proc = subprocess.run([str(cli), *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace")
        commands.append({"arguments": arguments, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
        return proc

    def export(name: str, path: Path) -> dict:
        freeze_schematic(path)
        target = out / (name + ".xml")
        proc = run(["sch", "export", "netlist", "--format", "kicadxml", "-o", str(target), str(path)])
        check(name + ": fresh native netlist export", proc.returncode == 0, {"returncode": proc.returncode, "file": str(target)})
        if proc.returncode or not target.is_file():
            raise RuntimeError(f"Fresh netlist export failed: {name}")
        return netlist(target)

    check("v1 remains leading electrical and layout design", profiles.get("leading_product") == "v1")
    common = export("COMMON", canonical)
    common_refs = set(common["parts"])
    check("canonical component count", len(common_refs) == profiles["canonical_component_count"], len(common_refs))
    check("canonical contains functional circuit only", not any(ref.startswith("H") or ref in {"J101", "J201", "TP6"} for ref in common_refs))
    erc_path = out / "COMMON_erc.json"
    proc = run(["sch", "erc", "--format", "json", "--severity-all", "--exit-code-violations", "-o", str(erc_path), str(canonical)])
    erc = load(erc_path) if erc_path.is_file() else {}
    violations = erc.get("violations", []) + [v for sheet in erc.get("sheets", []) for v in sheet.get("violations", [])]
    check("canonical fresh ERC zero without exclusions", proc.returncode == 0 and not violations and not erc.get("ignored_checks"), {"returncode": proc.returncode, "violations": len(violations), "ignored_checks": len(erc.get("ignored_checks", []))})

    # Confirm all symbol and footprint definitions needed for editing are local.
    local_symbols = sexpr((canonical.parent / "Meshcore.kicad_sym").read_text(encoding="utf-8-sig"))
    available_symbols = {value(item[1]) for item in children(local_symbols, "symbol")}
    unresolved = []
    for source in source_files(canonical):
        for symbol in children(sexpr(source.read_text(encoding="utf-8-sig")), "symbol"):
            lib_id = one(symbol, "lib_id")
            if lib_id and value(lib_id[1]).startswith("Meshcore:") and value(lib_id[1]).split(":", 1)[1] not in available_symbols:
                unresolved.append([relative(source, root), value(lib_id[1])])
    for ref, part in common["parts"].items():
        footprint = part["fields"].get("Footprint", "")
        if footprint.startswith("Meshcore:") and not (canonical.parent / "Meshcore.pretty" / (footprint.split(":", 1)[1] + ".kicad_mod")).is_file():
            unresolved.append([ref, footprint])
    dependency_sources = [*source_files(canonical), canonical.parent / "Meshcore.kicad_sym", *(canonical.parent / "Meshcore.pretty").glob("*.kicad_mod")]
    for source in dependency_sources:
        frozen[source] = sha256(source)
        for dependency in re.findall(r'\$\{KIPRJMOD\}/([^"\r\n]+)', source.read_text(encoding="utf-8-sig")):
            target = canonical.parent / dependency
            if not target.is_file():
                unresolved.append([relative(source, root), dependency])
            else:
                frozen[target.resolve()] = sha256(target)
    check("canonical project-local editing dependencies resolve", not unresolved, unresolved)

    canonical_groups = {frozenset(net["endpoints"]) for net in common["nets"].values() if net["endpoints"]}
    product_summaries = {}
    for product_id in selected:
        product = config["products"][product_id]
        profile = profiles["products"][product_id]
        invalid_overrides = []
        for ref, override in profile.get("physical_overrides", {}).items():
            allowed = {"Footprint"}
            # Physical connector/button names and ordering codes may differ;
            # functional component values/MPNs and assembly fits may not.
            if ref.startswith(("J", "SW")):
                allowed |= {"Value", "MPN", *[field for field in VARIANT_FIELDS if not field.startswith("Fit_")]}
            if ref not in common_refs or set(override) - allowed:
                invalid_overrides.append({"reference": ref, "forbidden_fields": sorted(set(override) - allowed)})
        check(product_id + ": physical profile cannot override functional values or assembly fits", not invalid_overrides, invalid_overrides)
        native = {}
        models = {}
        for board in product["boards"]:
            pcb = root / board["pcb"]
            if pcb.is_file():
                frozen[pcb] = sha256(pcb)
            if not board.get("schematic"):
                continue
            name = board["name"]
            sch = root / board["schematic"]
            native[name] = export(product_id + "_" + name, sch)
            model_path = sch.parent / "model.json"
            if model_path.is_file():
                models[name] = load(model_path)

        union = Union()
        endpoint_group = {}
        for board, data in native.items():
            for net_id, net in data["nets"].items():
                key = (board, net_id)
                union.find(key)
                for endpoint in net["endpoints"]:
                    endpoint_group[(board, *endpoint)] = key
        for bridge in profile.get("interconnects", []):
            for first_pin, second_pin in bridge["pin_pairs"]:
                first = (bridge["first"]["board"], bridge["first"]["reference"], str(first_pin))
                second = (bridge["second"]["board"], bridge["second"]["reference"], str(second_pin))
                if first in endpoint_group and second in endpoint_group:
                    union.join(endpoint_group[first], endpoint_group[second])
                else:
                    check(product_id + ": interconnect endpoint exists", False, [first, second])

        groups = defaultdict(set)
        location = {}
        all_parts = {}
        duplicate_refs = []
        for board, data in native.items():
            for net_id, net in data["nets"].items():
                groups[union.find((board, net_id))].update((board, ref, pin) for ref, pin in net["endpoints"])
            for ref, part in data["parts"].items():
                if ref in all_parts:
                    duplicate_refs.append(ref)
                all_parts[ref] = part
                location[ref] = board
        check(product_id + ": references unique across boards", not duplicate_refs, duplicate_refs)
        extras = {extra["reference"]: extra for extra in profile.get("extra_components", [])}
        check(product_id + ": exact functional and physical component set", set(all_parts) == common_refs | set(extras), {"missing": sorted((common_refs | set(extras)) - set(all_parts)), "unexpected": sorted(set(all_parts) - (common_refs | set(extras)))})
        allocations = Counter(ref for refs in profile["board_references"].values() for ref in refs)
        coverage = {
            "missing_references": sorted(set(all_parts) - set(allocations)),
            "unexpected_references": sorted(set(allocations) - set(all_parts)),
            "duplicate_references": sorted(ref for ref, count in allocations.items() if count != 1),
            "missing_boards": sorted(set(native) - set(profile["board_references"])),
            "unexpected_boards": sorted(set(profile["board_references"]) - set(native)),
        }
        check(product_id + ": board profile covers every native reference exactly once", not any(coverage.values()), coverage)
        wrong_board = []
        for board, refs in profile["board_references"].items():
            for ref in refs:
                if location.get(ref) != board:
                    wrong_board.append([ref, board, location.get(ref)])
        check(product_id + ": declared board allocation", not wrong_board, wrong_board)

        metadata = []
        for ref in sorted(common_refs & set(all_parts)):
            override = profile.get("physical_overrides", {}).get(ref, {})
            for field in COMPARED_FIELDS:
                expected = override.get(field, common["parts"][ref]["fields"].get(field, ""))
                actual = all_parts[ref]["fields"].get(field, "")
                if actual != expected:
                    metadata.append({"reference": ref, "field": field, "expected": expected, "actual": actual})
        check(product_id + ": canonical values, assembly variants and physical profile", not metadata, metadata)
        model_differences = []
        for board, model in models.items():
            model_parts = {part["ref"]: part for part in model["parts"]}
            if set(model_parts) != set(native[board]["parts"]):
                model_differences.append({"board": board, "reference_set": {"model_only": sorted(set(model_parts)-set(native[board]["parts"])), "native_only": sorted(set(native[board]["parts"])-set(model_parts))}})
            for ref in model_parts.keys() & native[board]["parts"].keys():
                part, actual = model_parts[ref], native[board]["parts"][ref]["fields"]
                expected = {"Value": part["value"], "Footprint": part["footprint"], "MPN": part.get("mpn", "")}
                for suffix, model_suffix, fit_key in [("NaIon", "", "fit_naion"), ("NaIon_NoCold", "_naion_no_cold", "fit_naion_no_cold"), ("LTO_2S", "_lto2s", "fit_lto2s")]:
                    expected["Value_" + suffix] = part.get("value" + model_suffix, part["value"])
                    expected["MPN_" + suffix] = part.get("mpn" + model_suffix, part.get("mpn", ""))
                    expected["Fit_" + suffix] = "yes" if part.get(fit_key, False) else "no"
                # Some mechanical net ties intentionally omit redundant variant fields.
                for field, wanted in expected.items():
                    if field not in actual and field not in {"Value", "Footprint", "MPN"}:
                        continue
                    if actual.get(field, "") != wanted:
                        model_differences.append({"board": board, "reference": ref, "field": field, "model": wanted, "native": actual.get(field, "")})
        check(product_id + ": available product models match native fields", not model_differences, model_differences)

        def joined_endpoints(board: str, ref: str, pin: str) -> set:
            key = endpoint_group.get((board, ref, pin))
            return groups[union.find(key)] if key else set()

        extra_failures = []
        anchors = profiles["net_anchors"]
        for ref, spec in extras.items():
            if ref not in all_parts:
                continue
            board = spec["board"]
            exported_pins = {pin for endpoint_board, endpoint_ref, pin in endpoint_group if endpoint_board == board and endpoint_ref == ref}
            if exported_pins != set(spec.get("pins", {})):
                extra_failures.append([ref, "exact declared electrical pin set", sorted(spec.get("pins", {})), sorted(exported_pins)])
            for field, wanted in spec["fields"].items():
                if all_parts[ref]["fields"].get(field, "") != wanted:
                    extra_failures.append([ref, field, wanted, all_parts[ref]["fields"].get(field, "")])
            for pin, net_name in spec.get("pins", {}).items():
                actual_group = joined_endpoints(board, ref, pin)
                if net_name is None:
                    if actual_group and actual_group != {(board, ref, pin)}:
                        extra_failures.append([ref, pin, "must remain NC", sorted(actual_group)])
                else:
                    anchor_ref, anchor_pin = anchors[net_name]
                    anchor = (location.get(anchor_ref), anchor_ref, anchor_pin)
                    if anchor not in actual_group:
                        extra_failures.append([ref, pin, "must join " + net_name, sorted(actual_group)])
        check(product_id + ": declared mechanical, testpoint and connector extras", not extra_failures, extra_failures)

        allowed_nc = {tuple(item) for item in profile.get("allowed_extra_nc_pins", [])}
        nc_failures = []
        for ref, pin in allowed_nc:
            group = joined_endpoints(location.get(ref), ref, pin)
            if group != {(location.get(ref), ref, pin)}:
                nc_failures.append([ref, pin, sorted(group)])
        check(product_id + ": permitted extra pins are explicitly NC", not nc_failures, nc_failures)
        projected = set()
        for endpoints in groups.values():
            reduced = frozenset((ref, pin) for _, ref, pin in endpoints if ref in common_refs and (ref, pin) not in allowed_nc)
            if reduced:
                projected.add(reduced)
        difference = canonical_groups ^ projected
        check(product_id + ": full native pin graph equals canonical circuit", not difference, [sorted(group) for group in sorted(difference, key=lambda item: sorted(item))])
        product_summaries[product_id] = {"version": product["version"], "native_components": len(all_parts), "canonical_components": len(common_refs), "physical_extras": len(extras), "projected_net_groups": len(projected), "models_checked": sorted(models)}

    changed_sources = [relative(path, root) for path, digest in frozen.items() if sha256(path) != digest]
    check("verification preserves native schematic/model/PCB source bytes", not changed_sources, changed_sources)
    report = {
        "status": "PASS" if all(item["passed"] for item in checks) else "FAIL",
        "leading_product": profiles["leading_product"],
        "authority": "Shared native circuit is the electrical authority; it derives from leading v1. Physical product schematics are checked projections, not automatically generated files.",
        "canonical": relative(canonical, root),
        "canonical_components": len(common_refs),
        "canonical_net_groups": len(canonical_groups),
        "products": product_summaries,
        "passed": sum(item["passed"] for item in checks),
        "total": len(checks),
        "checks": checks,
        "source_sha256": {relative(path, root): digest for path, digest in sorted(frozen.items())},
        "configuration_sha256": {relative(config_path, root): sha256(config_path), relative(profiles_path, root): sha256(profiles_path)},
        "commands": commands,
        "limits": "Native schematic equivalence/ERC and source preservation. This gate does not replace PCB DRC/parity, manufacture review or measurements. No accepted PCB is regenerated or synchronized by this command.",
    }
    (out / "circuit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "passed": report["passed"], "total": report["total"], "products": selected, "report": str(out / "circuit.json")}, ensure_ascii=False))
    if report["status"] != "PASS":
        print(json.dumps([item for item in checks if not item["passed"]], ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print("Circuit verification failed: " + str(error), file=sys.stderr)
        raise SystemExit(2)
