# Weapon domain (D&D 5e 2014)

## Rules catalogue

`rules_engine.dnd5e_2014.weapons.catalog` exposes the immutable SRD 5.1 catalogue through `WEAPON_CATALOG`, `get_weapon(key)`, and `list_weapons()`. The stable `weapon_key` belongs to an `Item` definition; a physical copy remains an ordinary `ItemInstance`.

The catalogue contains the 37 entries in the SRD simple/martial melee/ranged weapon tables. It stores rules data (damage expression/type, category, properties, normal/long range and versatile damage), not descriptive flavour text. See [SRD-ATTRIBUTION.md](../SRD-ATTRIBUTION.md).

## Character proficiency

`CharacterState.weapon_proficiencies` stores category identifiers (`simple_melee`, `simple_ranged`, `martial_melee`, `martial_ranged`) or a specific weapon key. An unproficient character can still make an attack; the proficiency bonus is simply omitted.

## Equipping

`WeaponEquipmentRepository` persists one equipped weapon instance per character and campaign. The database validates that the instance is active, belongs to that character, and refers to an item with a weapon key in the same campaign. Ownership changes and deactivation automatically clear the equipped reference.

`WeaponEquipmentService.attack_profile` derives the attack ability, attack bonus and damage modifier from the persisted weapon definition and the supplied character state. It does not accept client-provided attack or damage bonuses.

## Deliberate limitations

This is the domain foundation, not a complete combat action. Off-hand/dual-wield slots, hand occupancy, ammunition consumption, special weapon rules, attack action economy, and atomic application of damage to encounter and character hit points are future work. The existing combat resolver remains the single damage-resolution engine; a later use case must coordinate its result and both persistence updates in one transaction.
