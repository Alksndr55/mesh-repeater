"""Rebind the finite routing closure to a freshly rerun independent review.

Requires the preserved previous proofs. Does not edit CAD, expected source
hashes, issue dispositions, or acceptance conditions.
"""
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = ROOT / "archive/publication_previous_proofs/2026_10_12_before_refresh"
REVIEW = "audit/routing_geometry_2026_10_12/independent_final.json"
CLOSURE = "audit/routing_geometry_2026_10_12/closure_review.json"
HELPER = "tools/verify_v2_native_boards.py"
REPORT = ROOT / "audit/publication_2026_10_12/proof_refresh.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def method_without_workspace_assignment(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "WORKSPACE"
                           for target in node.targets)]
    assert len(assignments) == 1, "Expected exactly one WORKSPACE assignment"
    tree.body.remove(assignments[0])
    return ast.dump(tree, include_attributes=False)


def references_to_review(value):
    references = []
    if isinstance(value, dict):
        if value.get("path") == REVIEW and "sha256" in value:
            references.append(value)
        for child in value.values():
            references.extend(references_to_review(child))
    elif isinstance(value, list):
        for child in value:
            references.extend(references_to_review(child))
    return references


def main():
    checks = []

    def check(name, passed):
        checks.append({"name": name, "pass": bool(passed)})
        if not passed:
            raise RuntimeError(name)

    manifest = read(PREVIOUS / "manifest.json")
    check("Eight previous proofs preserved byte for byte",
          len(manifest["proofs"]) == 8 and all(
              sha(ROOT / row["backup_path"]) == row["sha256"]
              for row in manifest["proofs"]))
    old_review = read(PREVIOUS / REVIEW)
    old_closure = read(PREVIOUS / CLOSURE)
    closure = read(ROOT / CLOSURE)
    review = read(ROOT / REVIEW)
    historical = manifest["historical_method"]
    old_helper = ROOT / historical["backup_path"]
    check("Historical helper matches its original independent binding",
          sha(old_helper) == historical["sha256"]
          == old_review["inputs"][HELPER])
    check("Only the organizational WORKSPACE assignment changed in the helper",
          method_without_workspace_assignment(old_helper)
          == method_without_workspace_assignment(ROOT / HELPER))
    check("All preserved CAD sources remain unchanged",
          all(sha(ROOT / path) == digest for path, digest
              in manifest["CAD_sha256_before_refresh"].items()))
    check("Fresh independent review passes all original 132 conditions",
          review["ok"] is True and len(review["checks"]) == 132
          and all(row["pass"] for row in review["checks"])
          and [row["name"] for row in review["checks"]]
          == [row["name"] for row in old_review["checks"]])
    check("Fresh review used saved CAD without modification or refill",
          review["native_CAD_modified"] is False
          and review["refill_performed"] is False
          and review["routing_geometry_review_complete"] is True)
    check("Fresh independent measurements and geometry equal the prior proof",
          review["boards"] == old_review["boards"])
    check("Every fresh independent input hash matches its current file",
          all(sha(ROOT / path) == digest for path, digest
              in review["inputs"].items()))
    generated = {
        "audit/routing_geometry_2026_10_12/independent_final_native_measurements.json",
        *[f"audit/routing_geometry_2026_10_12/independent_final_{board}_drc.json"
          for board in ("POWER", "LOGIC", "SHIELD")],
    }
    check("Only regenerated proof inputs and the documented helper binding changed",
          set(review["inputs"]) == set(old_review["inputs"])
          and all(path in generated | {HELPER}
                  or digest == old_review["inputs"][path]
                  for path, digest in review["inputs"].items()))
    check("All 18 finite issue dispositions remain unchanged",
          len(closure["issues"]) == 18
          and len({row["id"] for row in closure["issues"]}) == 18
          and closure["issues"] == old_closure["issues"]
          and not closure["genuine_unapplied_safe_actions"])
    check("Closure itself is still the preserved original before rebinding",
          closure == old_closure)
    check("All other closure inputs remain hash-exact",
          all(row["path"] == REVIEW or sha(ROOT / row["path"]) == row["sha256"]
              for row in closure["inputs"]))
    check("Both actual board hashes match the preserved closure",
          all(sha(ROOT / row["path"]) == row["sha256"]
              for row in closure["boards"].values()))

    fresh_hash = sha(ROOT / REVIEW)
    references = references_to_review(closure)
    check("Exactly three closure pointers refer to the prior independent proof",
          len(references) == 3
          and all(row["sha256"] == sha(PREVIOUS / REVIEW) for row in references)
          and closure["current_independent_review"] == {
              "path": REVIEW, "sha256": sha(PREVIOUS / REVIEW)})
    for row in references:
        row["sha256"] = fresh_hash
    (ROOT / CLOSURE).write_text(json.dumps(closure, ensure_ascii=False, indent=2)
                              + "\n", encoding="utf-8")
    report = {
        "stage": "V2_PUBLICATION_FRESH_PROOF_CLOSURE_REBIND",
        "ok": True,
        "checks": checks,
        "CAD_modified": False,
        "exports_regenerated": False,
        "issue_dispositions_modified": False,
        "previous_proofs_manifest": {
            "path": (PREVIOUS / "manifest.json").relative_to(ROOT).as_posix(),
            "sha256": sha(PREVIOUS / "manifest.json"),
        },
        "historical_helper": historical,
        "current_helper": {"path": HELPER, "sha256": sha(ROOT / HELPER)},
        "independent_review": {"path": REVIEW, "sha256": fresh_hash},
        "closure": {"path": CLOSURE, "sha256": sha(ROOT / CLOSURE)},
        "change_scope": "Three derived pointers to a freshly rerun independent proof, including one nested evidence reference; all original issue dispositions, source hashes and acceptance conditions retained.",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"ok": True, "checks": len(checks),
                      "report": REPORT.relative_to(ROOT).as_posix()}))


if __name__ == "__main__":
    main()
