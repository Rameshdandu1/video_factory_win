"""Mechanical checks for the dependency rules in docs/architecture.md."""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "video_app"
LAYERS = {"api", "application", "domain", "infrastructure", "backends"}
ALLOWED_INTERNAL_IMPORTS = {
    "domain": {"domain"},
    "application": {"application", "domain"},
    "api": {"api", "application", "domain"},
    "infrastructure": {"infrastructure", "application", "domain"},
    "backends": {"backends", "application", "domain"},
}


def _internal_layer(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "video_app" and parts[1] in LAYERS:
        return parts[1]
    return None


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_layer_import_direction() -> None:
    violations: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        relative = path.relative_to(SOURCE_ROOT)
        if len(relative.parts) < 2 or relative.parts[0] not in LAYERS:
            continue
        source_layer = relative.parts[0]
        for module in _imports(path):
            target_layer = _internal_layer(module)
            if target_layer and target_layer not in ALLOWED_INTERNAL_IMPORTS[source_layer]:
                violations.append(f"{relative}: {source_layer} imports {module}")
    assert not violations, "Forbidden layer imports:\n" + "\n".join(sorted(violations))


def test_wan_imports_are_confined_to_adapter() -> None:
    violations: list[str] = []
    adapter_root = SOURCE_ROOT / "backends" / "wan21"
    for path in SOURCE_ROOT.rglob("*.py"):
        if path.is_relative_to(adapter_root):
            continue
        for module in _imports(path):
            if module == "wan" or module.startswith("wan."):
                violations.append(f"{path.relative_to(SOURCE_ROOT)} imports {module}")
    assert not violations, "Wan2.1 imports outside adapter:\n" + "\n".join(violations)

