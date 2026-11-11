import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES = {
    "models": {"api", "services"},
    "operations": {"api", "services", "repositories"},
    "rules_engine": {"api", "models", "services", "repositories"},
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



# Capability-package rules are intentionally expressed as forbidden edges:
# new dependencies require an explicit architecture decision and a test update.
PACKAGE_FORBIDDEN_IMPORTS = {
    "campaign": {
        "api",
        "bootstrap",
        "services.characters",
        "services.combat",
        "services.context",
        "services.llm_world",
        "services.providers",
        "services.turns",
    },
    "characters": {
        "api",
        "bootstrap",
        "services.campaign",
        "services.combat",
        "services.context",
        "services.llm_world",
        "services.providers",
        "services.turns",
        "services.world",
    },
    "combat": {
        "api",
        "bootstrap",
        "services.campaign",
        "services.context",
        "services.llm_world",
        "services.providers",
        "services.turns",
        "services.world",
    },
    "context": {
        "api",
        "bootstrap",
        "services.campaign",
        "services.characters",
        "services.combat",
        "services.llm_world",
        "services.providers",
        "services.turns",
    },
    "llm_world": {
        "api",
        "bootstrap",
        "database",
        "repositories",
        "services.campaign",
        "services.characters",
        "services.combat",
        "services.context",
        "services.providers",
        "services.turns",
        "services.world",
    },
    "providers": {
        "api",
        "bootstrap",
        "database",
        "models",
        "operations",
        "repositories",
        "rules_engine",
        "services",
    },
    "turns": {
        "api",
        "bootstrap",
    },
    "world": {
        "api",
        "bootstrap",
        "services.campaign",
        "services.combat",
        "services.context",
        "services.llm_world",
        "services.providers",
        "services.turns",
    },
}


def _absolute_module_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
    return imports


def test_capability_packages_respect_dependency_matrix():
    violations = []

    for package, forbidden_modules in PACKAGE_FORBIDDEN_IMPORTS.items():
        package_path = ROOT / "services" / package
        for path in sorted(package_path.rglob("*.py")):
            imports = _absolute_module_imports(path.read_text(encoding="utf-8"))
            forbidden = sorted(
                imported
                for imported in imports
                if any(
                    imported == blocked or imported.startswith(blocked + ".")
                    for blocked in forbidden_modules
                )
            )
            if forbidden:
                violations.append(
                    f"{path.relative_to(ROOT)} imports forbidden module(s): "
                    f"{', '.join(forbidden)}"
                )

    assert not violations, (
        "Capability-package dependency matrix was violated:\\n"
        + "\\n".join(violations)
    )
