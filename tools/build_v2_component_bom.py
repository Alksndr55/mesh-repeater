"""Export the two saved V2 models; removable jumper/fasteners remain separate.

Does not edit models, PCB files, frozen baseline or version1.0. Rerun after the
final saved CAD to refresh exact mechanical MPN/footprints and hashes.
"""
from pathlib import Path
import csv
import hashlib
import json
import re
from v2_feature_contract import FEATURE_PATH, load_feature, feature_checks

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "design" / "v2_electrical_contract.json"


def minimum_order_price(offer):
    """Price each component at its purchasable MOQ, preserving tier meaning."""
    minimum = int(offer.get("minimum_order", offer.get("minimum_order_multiple", 1)))
    tiers = []
    for key, value in offer.items():
        match = re.fullmatch(r"price_rub_each_qty(\d+)(_listed)?", key)
        if match and int(match.group(1)) <= minimum:
            tiers.append((int(match.group(1)), not bool(match.group(2)), value))
    if not tiers:
        return "", "No verified price tier for MOQ " + str(minimum)
    threshold, _, price = max(tiers, key=lambda item: (item[0], item[1]))
    return price, "each at quantity " + str(minimum) + "; supplier tier from " + str(threshold)


def main():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    feature_contract = load_feature(CONTRACT)
    source = {p["reference"]: p for p in contract["parts"]}
    selection_path = ROOT / "docs" / "mechanical_selection.json"
    selected = {}
    cable_mates = {}
    if selection_path.exists():
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        selected = {ref: item for item in selection.get("parts", []) for ref in item.get("refs", [])}
        cable_mates = {ref: item for item in selection.get("accessories", []) for ref in item.get("mate_headers", [])}
    rows = []
    inputs = {str(CONTRACT.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(CONTRACT.read_bytes()).hexdigest()}
    if selection_path.exists():
        inputs[str(selection_path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(selection_path.read_bytes()).hexdigest()
    seen_original = []
    removed_mechanical = {}
    saved_models = {}
    procurement_path = ROOT / "audit" / "ina219_and_vertical_2026_10_12" / "procurement.json"
    procurement = json.loads(procurement_path.read_text(encoding="utf-8")) if feature_contract else {}
    offers = {row["mpn"]: row for row in procurement.get("offers", [])}
    ali_path = ROOT / "audit" / "vertical_interconnect_2026_10_12" / "ali_pair_selection.json"
    ali = json.loads(ali_path.read_text(encoding="utf-8")) if feature_contract else {}
    if feature_contract:
        for evidence_path in [FEATURE_PATH, ROOT / "tools" / "v2_feature_contract.py", procurement_path, ali_path]:
            inputs[str(evidence_path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    for project in ["MeshRepeater2_Power", "MeshRepeater2_Logic"]:
        path = ROOT / "design" / project / "model.json"
        payload = path.read_bytes()
        model = json.loads(payload.decode("utf-8"))
        board = model["partition_board"]
        saved_models[board] = model
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
            # These are board-mounted Ali parts. The old mechanical selection
            # still records the removed IDC cable revision; never buy it for A2.
            connector_offer = None
            if feature_contract and ref in {"J101", "J201"}:
                connector_offer = ali["male" if ref == "J101" else "female"]
                expected_mpn = "E-SIMPO L35mm A3C6 2x6P" if ref == "J101" else "MTJ H8.5 2X6P 10PCS"
                assert p["mpn"] == expected_mpn and p["vendor_url"] == connector_offer["url"], (ref, p["mpn"], p["vendor_url"])
                selection_item = {"mpn": p["mpn"], "footprint": p.get("source_footprint_before_v2_graphic_variant", p["footprint"]), "vendor_url": p["vendor_url"], "stock": connector_offer["stock_displayed"], "stock_checked": ali["date"], "article": connector_offer["product_id"]}
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
            current_offer = offers.get(mpn_na, {}) if feature_contract and ref in {"U12", "R71", "R72", "R73", "C63", "C64"} else {}
            current_price, current_price_basis = minimum_order_price(current_offer) if current_offer else ("", "")
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
            elif current_offer:
                stock_status = "New INA219 position; checked offer " + procurement["checked_date_omsk"] + "; stock " + str(current_offer.get("stock_units", "")) + "; " + current_offer.get("stock_location", current_offer.get("shop", ""))
            elif connector_offer:
                stock_status = "Ali vertical board connector; current selected model/package; nominal mating only, incoming samples unqualified"
            elif feature_contract and ref in {"U12", "R71", "R72", "R73", "C63", "C64"}:
                stock_status = "New INA219 position; selected MPN, current stock not rechecked"
            elif selection_item:
                stock_status = "Selected mechanical card; physical model synchronization " + ("confirmed" if physical_footprint == selection_item.get("footprint") else "pending")
            elif ref in {"M1", "M2"}:
                stock_status = "Module ordered separately; actual incoming module qualification pending"
            else:
                stock_status = "Inherited S4.16 procurement data; current stock not rechecked"
            rows.append({
                "Board": board, "Reference": ref, "Kind": p["kind"], "Quantity_Physical_Positions": 1,
                "Value_NaIon_COLD": p["value"] if p["kind"] == "MountingHole" else variant["Value_NaIon"] if variant else p["value"],
                "Fit_NaIon_COLD": fit_na,
                "Value_NaIon_NoCOLD": p["value"] if p["kind"] == "MountingHole" else variant["Value_NaIon_NoCold"] if variant else p.get("value_naion_no_cold", p["value"]),
                "Fit_NaIon_NoCOLD": fit_nc,
                "Value_LTO_2S": p["value"] if p["kind"] == "MountingHole" else variant["Value_LTO_2S"] if variant else p.get("value_lto2s", p["value"]),
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
                "Mechanical_Selection_URL": selection_item.get("vendor_url", selection_item.get("dan_url", "")),
                "Mechanical_Selection_Stock": selection_item.get("stock", ""),
                "Mechanical_Selection_Checked": selection_item.get("stock_checked", ""),
                "Procurement_Status": stock_status,
                "Current_Offer_URL": current_offer.get("url", connector_offer["url"] if connector_offer else ""),
                "Current_Offer_Stock": current_offer.get("stock_units", connector_offer["stock_displayed"] if connector_offer else ""),
                "Current_Offer_Checked": procurement.get("checked_date_omsk", "") if current_offer else ali.get("date", "") if connector_offer else "",
                "Current_Offer_Minimum_Order": current_offer.get("minimum_order", current_offer.get("minimum_order_multiple", "")) if current_offer else connector_offer.get("lot_quantity", connector_offer.get("pack_quantity_in_option_and_title", "")) if connector_offer else "",
                "Current_Offer_Price_RUB": current_price if current_offer else connector_offer.get("lot_price_rub", connector_offer.get("price_rub_for_selected_option", "")) if connector_offer else "",
                "Current_Offer_Price_Basis": current_price_basis if current_offer else "one lot/pack; not one connector" if connector_offer else "",
                "Note": p.get("note", "") + (
                    " Cable mate: " + cable_mates[ref]["mpn"] +
                    "; 4x Connfly T-DS1071-SC600 per connector; quantities and purchase links in bom/DAN_NEW_PARTS.csv."
                    if ref in cable_mates and not (feature_contract and ref in {"J101", "J201"}) else ""),
            })
    assert len(seen_original) == len(set(seen_original))
    assert not (set(seen_original) & set(removed_mechanical))
    assert set(seen_original) | set(removed_mechanical) == set(source)
    assert len(source) == 167
    feature_proof = feature_checks(saved_models, feature_contract)
    assert all(check["pass"] for check in feature_proof), [check for check in feature_proof if not check["pass"]]
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
    excludes = ["removable J11 jumper shunt only (R71 measurement resistor is included)", "spacers/bolts/nuts/washers", "separate battery cell purchase", "SH1 removed by explicit mechanical decision"]
    if not feature_contract:
        excludes = ["external cable housings and contacts", "ribbon cable and strain relief"] + excludes
    result = {"stage": "SAVED_MODEL_COMPONENT_INVENTORY_NOT_FULL_PROCUREMENT_RELEASE", "date": "2026-10-12", "baseline_commit": contract["published_source_commit"], "inputs": inputs, "snapshot_stable": True, "changed_inputs": changed_inputs, "rows": len(rows), "baseline_original_positions": len(source), "original_positions_retained": len(seen_original), "explicit_removed_mechanical_positions": list(removed_mechanical.values()), "baseline_positions_fully_accounted": len(seen_original) + len(removed_mechanical) == 167, "bom_sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "excludes": excludes, "additional_procurement_list": "DAN_NEW_PARTS for remaining accessories; J101/J201 Ali parts are included here and supersede prior IDC/cable selection", "feature_checks": feature_proof, "new_INA219_positions": [r["Reference"] for r in rows if r["Reference"] in {"U12", "R71", "R72", "R73", "C63", "C64"}], "model_selection_sync_pending_refs": [r["Reference"] for r in rows if r["Procurement_Status"].endswith("pending") and r["Mechanical_Selection_Footprint"]]}
    audit = ROOT / "audit" / "v2_component_bom.json"
    audit.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
