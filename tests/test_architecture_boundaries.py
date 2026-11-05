import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES = {
    "models": {"api", "services"},
    "operations": {"api", "services", "repositories"},
    "rules_engine": {"api", "services", "repositories"},
    "repositories": {"api", "services"},
    "services": {"api"},
}


def _import_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def test_core_layers_do_not_import_inward_or_sideways():
    violations = []

    for layer, forbidden_roots in BOUNDARIES.items():
        layer_path = ROOT / layer
        if not layer_path.is_dir():
            continue
        for path in sorted(layer_path.rglob("*.py")):
            imports = _import_roots(path.read_text(encoding="utf-8"))
            forbidden = sorted(imports & forbidden_roots)
            if forbidden:
                violations.append(
                    f"{path.relative_to(ROOT)} imports forbidden layer(s): "
                    f"{', '.join(forbidden)}"
                )

    assert not violations, (
        "Architectural dependency boundaries were violated:\n"
        + "\n".join(violations)
    )
