"""Verify the saved V2 contract against native S4.16 pads, without editing CAD."""
from pathlib import Path
import hashlib
import json
import pcbnew

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
CONTRACT_PATH = ROOT / "design" / "v2_electrical_contract.json"
SOURCE = WORKSPACE / "design" / "Meshcore_NaIon" / "Meshcore_NaIon.kicad_pcb"


def main():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    board = pcbnew.LoadBoard(str(SOURCE))
    parts = {p["reference"]: p for p in contract["parts"]}
    errors = []
    pad_count = 0
    unique = set()
    connected = 0
    no_connect = 0
    for footprint in board.GetFootprints():
        ref = footprint.GetReference()
        if ref not in parts:
            errors.append([ref, "missing in contract"])
            continue
        for pad in footprint.Pads():
            pin = pad.GetNumber()
            if not pin:
                continue
            unique.add((ref, pin))
            pad_count += 1
            expected = parts[ref]["exact_netpins"].get(pin)
            if expected is None:
                errors.append([ref, pin, "numbered pad missing in contract"])
                continue
            actual = pad.GetNetname()
            if expected["no_connect"]:
                no_connect += 1
                # KiCad quotes slashes differently in PCB and XML automatic NC
                # names. The functional invariant is explicitly isolated pin.
                if not actual.startswith("unconnected-"):
                    errors.append([ref, pin, actual, "expected deliberately unconnected"])
            else:
                connected += 1
                if actual != expected["native_net"]:
                    errors.append([ref, pin, actual, expected["native_net"]])
    expected_nodes = {(ref, pin) for ref, p in parts.items() for pin in p["exact_netpins"]}
    if unique != expected_nodes:
        errors.append(["pad node sets differ", sorted(unique - expected_nodes), sorted(expected_nodes - unique)])
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if source_hash != contract["source_inputs"]["pcb"]["sha256"]:
        errors.append(["source hash changed"])
    result = {
        "stage": "SOURCE_S4_16_AND_PROPOSED_PARTITION_ONLY",
        "final_V2_CAD_verified": False,
        "contract_sha256": hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        "source_pcb_sha256": source_hash,
        "footprints": len(board.GetFootprints()),
        "original_contract_parts": len(parts),
        "physical_numbered_pads": pad_count,
        "unique_ref_pin_pairs": len(unique),
        "connected_physical_pads": connected,
        "deliberate_no_connect_physical_pads": no_connect,
        "encoding_U_FFFD_count": CONTRACT_PATH.read_text(encoding="utf-8").count(chr(65533)),
        "errors": errors,
        "ok": not errors,
    }
    out = ROOT / "audit" / "v2_electrical_contract_baseline.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
