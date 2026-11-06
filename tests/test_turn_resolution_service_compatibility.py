import services.turn_resolution_service as legacy_module
import services.turns as turns_package
import services.turns.turn_resolution_service as canonical_module


def test_legacy_turn_resolution_imports_reexport_canonical_objects():
    assert legacy_module.TurnResolutionPlan is canonical_module.TurnResolutionPlan
    assert legacy_module.TurnResolutionService is canonical_module.TurnResolutionService
    assert legacy_module.TurnResolutionServiceError is canonical_module.TurnResolutionServiceError


def test_turns_package_exports_canonical_resolution_types():
    assert turns_package.TurnResolutionPlan is canonical_module.TurnResolutionPlan
    assert turns_package.TurnResolutionService is canonical_module.TurnResolutionService
    assert turns_package.TurnResolutionServiceError is canonical_module.TurnResolutionServiceError
