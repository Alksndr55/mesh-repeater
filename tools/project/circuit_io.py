"""Small, dependency-free readers for the shared KiCad circuit gate.

This module never writes native KiCad sources or modifies PCB geometry.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sexpr(text: str) -> list:
    stack: list[list] = []
    result = None
    for token in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text):
        if token == "(":
            item: list = []
            if stack:
                stack[-1].append(item)
            stack.append(item)
        elif token == ")":
            if not stack:
                raise ValueError("Unbalanced KiCad expression")
            result = stack.pop()
        else:
            if not stack:
                raise ValueError("Token outside KiCad expression")
            stack[-1].append(token)
    if stack or not isinstance(result, list):
        raise ValueError("Incomplete KiCad expression")
    return result


def value(token: str) -> str:
    return json.loads(token) if token.startswith('"') else token


def children(tree: list, tag: str) -> list[list]:
    return [item for item in tree if isinstance(item, list) and item and item[0] == tag]


def one(tree: list, tag: str) -> list | None:
    return next(iter(children(tree, tag)), None)


def properties(tree: list) -> dict[str, str]:
    return {value(item[1]): value(item[2]) for item in children(tree, "property")}


def source_files(root_schematic: Path) -> list[Path]:
    """Follow only the hierarchy actually referenced by the root schematic."""
    seen: set[Path] = set()

    def visit(path: Path) -> None:
        path = path.resolve()
        if path in seen:
            return
        seen.add(path)
        tree = sexpr(path.read_text(encoding="utf-8-sig"))
        for sheet in children(tree, "sheet"):
            target = properties(sheet).get("Sheetfile")
            if not target:
                raise ValueError(f"Sheet without Sheetfile in {path}")
            visit(path.parent / target)

    visit(root_schematic)
    return sorted(seen)


def netlist(path: Path) -> dict:
    tree = ET.parse(path).getroot()
    parts = {}
    for comp in tree.findall("components/comp"):
        ref = comp.get("ref")
        if ref in parts:
            raise ValueError(f"Duplicate reference {ref} in {path}")
        fields = {field.get("name"): field.text or "" for field in comp.findall("fields/field")}
        fields["Value"] = comp.findtext("value") or ""
        fields["Footprint"] = comp.findtext("footprint") or ""
        parts[ref] = {"fields": fields}
    nets = {}
    for net in tree.findall("nets/net"):
        endpoints = {(node.get("ref"), node.get("pin")) for node in net.findall("node")}
        nets[net.get("code")] = {"name": net.get("name"), "endpoints": endpoints}
    return {"parts": parts, "nets": nets}


class Union:
    def __init__(self) -> None:
        self.parents: dict[tuple, tuple] = {}

    def find(self, key: tuple) -> tuple:
        if key not in self.parents:
            self.parents[key] = key
        if self.parents[key] != key:
            self.parents[key] = self.find(self.parents[key])
        return self.parents[key]

    def join(self, first: tuple, second: tuple) -> None:
        self.parents[self.find(first)] = self.find(second)
