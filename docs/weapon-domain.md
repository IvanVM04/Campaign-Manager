# Weapon domain (D&D 5e 2014)

## Rules catalogue

`rules_engine.dnd5e_2014.weapons.catalog` exposes the immutable SRD 5.1 catalogue through `WEAPON_CATALOG`, `get_weapon(key)`, and `list_weapons()`. The stable `weapon_key` belongs to an `Item` definition; a physical copy remains an ordinary `ItemInstance`.

The catalogue contains the 37 entries in the SRD simple/martial melee/ranged weapon tables. It stores rules data (damage expression/type, category, properties, normal/long range and versatile damage), not descriptive flavour text. See [SRD-ATTRIBUTION.md](../SRD-ATTRIBUTION.md).

## Character proficiency

`CharacterState.weapon_proficiencies` stores category identifiers (`simple_melee`, `simple_ranged`, `martial_melee`, `martial_ranged`) or a specific weapon key. An unproficient character can still make an attack; the proficiency bonus is simply omitted.

## Equipment ownership

Physical ownership remains canonical on `item_instances.owner_id`. Equipped state is a character equipment projection, not a second inventory or ownership record. Migration 026 introduces `equipped_items`, keyed by campaign, character and slot; each physical instance can occupy at most one slot. Existing `equipped_weapons` rows are migrated to `main_hand` without losing ownership.

Item definitions may declare one canonical equipment slot: `main_hand`, `off_hand`, `body`, `head`, `hands`, `feet`, `cloak`, `neck`, `ring_1`, `ring_2`, `waist`, `wondrous`, or `ammunition`. Weapon definitions default to `main_hand` for compatibility and may use either hand slot. Armor definitions use `armor_key` from the D&D 5e (2014) catalogue: body armor occupies `body`, while a shield occupies `off_hand`. A single item cannot be both a weapon and armor. Equipment is limited to persisted player characters in this slice; NPC equipment remains deferred.

The database enforces that an equipped instance is active, owned by the character, matches the item's declared slot, and belongs to the same campaign. Ownership transfer, deactivation, deletion, and character deletion clear equipment projections automatically. Equipped item identity and slot are immutable; replace an assignment rather than mutating it in place. Equipment mutations increment the campaign state revision.

`WeaponEquipmentRepository` is now the compatibility adapter for the generic equipment projection. Its legacy `equip` / `get_equipped` methods map to `main_hand`; generic callers can list slots, equip into a slot, or unequip one slot. `WeaponEquipmentService.attack_profile` continues deriving attack values from the main-hand weapon definition and trusted character state.

## Deliberate limitations

This is an ownership and slot lifecycle foundation with initial armor integration, not a complete equipment rules engine. Player-character AC is derived from equipped body armor, Dexterity and an optional shield when listing equipment or creating an encounter; attack resolution recalculates a player target's current AC from equipment. Armor proficiency, Strength-based speed penalties, class-feature AC alternatives, NPC equipment, two-handed/off-hand action rules, ammunition consumption, magic item effects and encumbrance remain deferred. The existing combat resolver remains the single damage-resolution engine.
