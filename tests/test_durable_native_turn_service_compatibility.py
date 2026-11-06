from services.durable_native_turn_service import (
    DurableNativeTurnError as LegacyDurableNativeTurnError,
)
from services.durable_native_turn_service import (
    DurableNativeTurnService as LegacyDurableNativeTurnService,
)
from services.turns.durable_native_turn_service import (
    DurableNativeTurnError,
    DurableNativeTurnService,
)


def test_legacy_coordinator_imports_reexport_canonical_objects():
    assert LegacyDurableNativeTurnError is DurableNativeTurnError
    assert LegacyDurableNativeTurnService is DurableNativeTurnService
