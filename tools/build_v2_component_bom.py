"""Export the two saved V2 models; cable parts/fasteners remain a separate BOM.

Does not edit models, PCB files, frozen baseline or version1.0. Rerun after the
final saved CAD to refresh exact mechanical MPN/footprints and hashes.
"""
from pathlib import Path
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "design" / "v2_electrical_contract.json"


def main():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    source = {p["reference"]: p for p in contract["parts"]}
    selection_path = ROOT / "docs" / "mechanical_selection.json"
    selected = {}
    if selection_path.exists():
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        selected = {ref: item for item in selection.get("parts", []) for ref in item.get("refs", [])}
    rows = []
    inputs = {str(CONTRACT.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(CONTRACT.read_bytes()).hexdigest()}
    if selection_path.exists():
        inputs[str(selection_path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(selection_path.read_bytes()).hexdigest()
    seen_original = []
    removed_mechanical = {}
    for project in ["MeshRepeater2_Power", "MeshRepeater2_Logic"]:
        path = ROOT / "design" / project / "model.json"
        payload = path.read_bytes()
        model = json.loads(payload.decode("utf-8"))
        board = model["partition_board"]
        inputs[str(path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(payload).hexdigest()
        variant_path = ROOT / "audit" / (project + "_footprint_variants.json")
        graphical = {}
        if variant_path.exists():
            variant_payload = variant_path.read_bytes()
            variant_record = json.loads(variant_payload.decode("utf-8"))
            assert variant_record["engineering_geometry_and_mpn_values_unchanged"] is True
            assert variant_record["invariant_before"] == variant_record["invariant_after_with_original_identifiers"]
            graphical = {entry["ref"]: entry for entry in variant_record["maps"]}
            inputs[str(variant_path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(variant_payload).hexdigest()
        if board == "POWER":
            shield = model.get("board", {}).get("shield", {})
            if shield.get("frame_decision") == "removed_after_independent_geometry_review" and shield.get("frame_fitted") is False:
                removed_mechanical["SH1"] = {"baseline_reference": "SH1", "kind": "mechanical_frame", "decision": "removed_after_independent_geometry_review", "fit_all_variants": "no", "buy_all_variants": "no", "proof": "audit/v2_frame_mount_review.json", "electrical_scope": "No functional circuit/variant change; original four GND frame lands removed with the mechanical frame"}
        for p in model["parts"]:
            ref = p["ref"]
            old = source.get(ref)
            variant = old["assembly_variant_row"] if old else None
            feature = p["kind"] in {"TestPoint", "MountingHole", "NetTie"}
            selection_item = selected.get(ref, {})
            physical_footprint = p["footprint"]
            if p.get("source_footprint_before_v2_graphic_variant"):
                graphical_record = graphical[ref]
                assert graphical_record["graphic_variant"] == p["footprint"]
                physical_footprint = p["source_footprint_before_v2_graphic_variant"]
                assert graphical_record["approved_selected_footprint"] == physical_footprint
                assert graphical_record["same_pads_fab_courtyard_3d_mpn_package"] is True
            fit_na = variant["Fit_NaIon"] if variant else "yes" if p.get("fit_naion", True) else "no"
            fit_nc = variant["Fit_NaIon_NoCold"] if variant else "yes" if p.get("fit_naion_no_cold", True) else "no"
            fit_lto = variant["Fit_LTO_2S"] if variant else "yes" if p.get("fit_lto2s", True) else "no"
            mpn_na = p.get("mpn", "")
            mpn_lto = p.get("mpn_lto2s", mpn_na)
            mpn_nc = p.get("mpn_naion_no_cold", mpn_na)
            if old:
                seen_original.append(ref)
                # Preserve alternate functional ordering numbers, while the
                # exact chosen mechanical part applies to every fitted variant.
                if variant["MPN_LTO_2S"] != variant["MPN_NaIon"]:
                    mpn_lto = variant["MPN_LTO_2S"]
                if variant["MPN_NaIon_NoCold"] != variant["MPN_NaIon"]:
                    mpn_nc = variant["MPN_NaIon_NoCold"]
            if feature:
                stock_status = "PCB feature; do not buy as a component"
            elif selection_item:
                stock_status = "Selected mechanical card; physical model synchronization " + ("confirmed" if physical_footprint == selection_item.get("footprint") else "pending")
            elif ref in {"M1", "M2"}:
                stock_status = "Module ordered separately; actual incoming module qualification pending"
            else:
                stock_status = "Inherited S4.16 procurement data; current stock not rechecked"
            rows.append({
                "Board": board, "Reference": ref, "Kind": p["kind"], "Quantity_Physical_Positions": 1,
                "Value_NaIon_COLD": variant["Value_NaIon"] if variant else p["value"],
                "Fit_NaIon_COLD": fit_na,
                "Value_NaIon_NoCOLD": variant["Value_NaIon_NoCold"] if variant else p.get("value_naion_no_cold", p["value"]),
                "Fit_NaIon_NoCOLD": fit_nc,
                "Value_LTO_2S": variant["Value_LTO_2S"] if variant else p.get("value_lto2s", p["value"]),
                "Fit_LTO_2S": fit_lto,
                "MPN_NaIon_COLD": mpn_na, "MPN_NaIon_NoCOLD": mpn_nc, "MPN_LTO_2S": mpn_lto,
                "Saved_Model_Footprint": p["footprint"],
                "Physical_Package_Footprint": physical_footprint,
                "Buy_Component_NaIon_COLD": "no" if feature else fit_na,
                "Buy_Component_NaIon_NoCOLD": "no" if feature else fit_nc,
                "Buy_Component_LTO_2S": "no" if feature else fit_lto,
                "Group": p.get("group", ""), "Original_S4_16_Reference": ref if old else "",
                "Vendor_URL_In_Model": p.get("vendor_url", ""),
                "Mechanical_Selection_MPN": selection_item.get("mpn", ""),
                "Mechanical_Selection_Article": selection_item.get("article", ""),
                "Mechanical_Selection_Footprint": selection_item.get("footprint", ""),
                "Mechanical_Selection_URL": selection_item.get("dan_url", ""),
                "Mechanical_Selection_Stock": selection_item.get("stock", ""),
                "Mechanical_Selection_Checked": selection_item.get("stock_checked", ""),
                "Procurement_Status": stock_status, "Note": p.get("note", ""),
            })
    assert len(seen_original) == len(set(seen_original))
    assert not (set(seen_original) & set(removed_mechanical))
    assert set(seen_original) | set(removed_mechanical) == set(source)
    assert len(source) == 167
    if removed_mechanical:
        frame_review = json.loads((ROOT / "audit" / "v2_frame_mount_review.json").read_text(encoding="utf-8"))
        assert frame_review["accepted_decision"]["choice"] == "C"
        assert frame_review["accepted_decision"]["SH1"] == "removed"
    changed_inputs = [relative for relative, digest in inputs.items() if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest]
    assert not changed_inputs, changed_inputs
    out = ROOT / "bom" / "V2_COMPONENT_BOM.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = {"stage": "SAVED_MODEL_COMPONENT_INVENTORY_NOT_FULL_PROCUREMENT_RELEASE", "date": "2026-10-11", "baseline_commit": contract["published_source_commit"], "inputs": inputs, "snapshot_stable": True, "changed_inputs": changed_inputs, "rows": len(rows), "baseline_original_positions": len(source), "original_positions_retained": len(seen_original), "explicit_removed_mechanical_positions": list(removed_mechanical.values()), "baseline_positions_fully_accounted": len(seen_original) + len(removed_mechanical) == 167, "bom_sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "excludes": ["external cable housings and contacts", "ribbon cable and strain relief", "shunt", "spacers/bolts/nuts/washers", "separate battery cell purchase", "SH1 removed by explicit mechanical decision"], "additional_procurement_list": "DAN_NEW_PARTS (prepared by mechanical selection task)", "model_selection_sync_pending_refs": [r["Reference"] for r in rows if r["Procurement_Status"].endswith("pending") and r["Mechanical_Selection_Footprint"]]}
    audit = ROOT / "audit" / "v2_component_bom.json"
    audit.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
