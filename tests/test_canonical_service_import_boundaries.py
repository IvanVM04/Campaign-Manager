"""Regression checks for migrated capability-package import boundaries."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# These production modules have completed their migration to capability
# packages. Keep this list explicit: other services still legitimately use
# compatibility paths while their migrations are pending.
MIGRATED_PRODUCTION_MODULES = (
    "app.py",
    "api/errors.py",
    "bootstrap/campaign_runtime.py",
    "services/campaign_turn_service.py",
    "services/dm_service.py",
    "services/turns/durable_native_turn_service.py",
    "services/legacy_silly_tavern_turn_service.py",
    "services/mechanics_adjudicator.py",
    "services/silly_tavern_integration_service.py",
    "services/turn_resolution_service.py",
)

LEGACY_IMPORTS = {
    "services.campaign_state_service",
    "services.character_applier",
    "services.character_service",
    "services.context_builder",
    "services.llm_world_extractor",
    "services.world_service",
}


def _absolute_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)

    return imports


def test_migrated_production_modules_do_not_use_flat_service_imports():
    violations = []

    for relative_path in MIGRATED_PRODUCTION_MODULES:
        path = ROOT / relative_path
        imports = _absolute_imports(path.read_text(encoding="utf-8"))
        legacy = sorted(
            imported
            for imported in imports
            if any(
                imported == legacy or imported.startswith(legacy + ".")
                for legacy in LEGACY_IMPORTS
            )
        )
        if legacy:
            violations.append(f"{relative_path}: {', '.join(legacy)}")

    assert not violations, (
        "Migrated production modules must use canonical capability packages; "
        "legacy imports found:\n" + "\n".join(violations)
    )
