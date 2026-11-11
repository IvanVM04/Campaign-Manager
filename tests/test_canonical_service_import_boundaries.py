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
    "services/dm_service.py",
    "services/turns/mechanics_adjudicator.py",
    "services/llm_world/operation_parser.py",
    "services/campaign/persistent_effect_service.py",
    "services/campaign/effective_condition_service.py",
    "services/campaign_turn_service.py",
    "services/turns/durable_native_turn_service.py",
    "services/legacy_silly_tavern_turn_service.py",
    "services/silly_tavern_integration_service.py",
    "services/turns/turn_resolution_service.py",
)

LEGACY_IMPORTS = {
    "services.campaign_runtime",
    "services.campaign_state_service",
    "services.character_applier",
    "services.character_service",
    "services.context_builder",
    "services.durable_native_turn_service",
    "services.llm_world_extractor",
    "services.llm_world_prompt_builder",
    "services.llm_world_response_parser",
    "services.context_ranker",
    "services.context_expander",
    "services.context_renderer",
    "services.memory_search_service",
    "services.mechanics_adjudicator",
    "services.operation_parser",
    "services.persistent_effect_service",
    "services.effective_condition_service",
    "services.world_serializer",
    "services.world_item_applier",
    "services.world_entity_applier",
    "services.llm_extraction_errors",
    "services.llm_provider",
    "services.ollama_provider",
    "services.fake_llm_provider",
    "services.llm_settings",
    "services.combat_encounter_service",
    "services.combat_attack_service",
    "services.weapon_equipment_service",
    "services.turn_execution_lock",
    "services.turn_resolution_service",
    "services.world_applier",
    "services.world_service",
    "services.world_relation_applier",
    "services.world_resource_applier",
    "services.character_creation_service",
    "services.campaign_clock_service",
    "services.durable_turn_challenge_state_service",
    "services.durable_turn_clarification_submission_service",
    "services.durable_turn_manual_roll_submission_service",
    "services.durable_turn_narration_service",
    "services.durable_turn_preparation_mapper",
    "services.durable_turn_prepared_commit_service",
    "services.durable_turn_result_mapper",
    "services.turn_resolution_codec",
    "services.llm_world_context_renderer",
    "services.llm_world_proposal_prompt_builder",
    "services.llm_world_proposal_validator",
    "services.world_state_port",
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


def test_removed_mechanics_adjudicator_compatibility_module_is_absent():
    assert not (ROOT / "services" / "mechanics_adjudicator.py").exists()


def test_removed_operation_parser_compatibility_module_is_absent():
    assert not (ROOT / "services" / "operation_parser.py").exists()


def test_removed_effect_service_compatibility_modules_are_absent():
    assert not (ROOT / "services" / "persistent_effect_service.py").exists()
    assert not (ROOT / "services" / "effective_condition_service.py").exists()
