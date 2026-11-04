# D&D 5e (2014) armor rules foundation

This increment adds the deterministic SRD 5.1 armor catalogue and Armor Class
calculation to the rules engine. It does not yet connect armor definitions to
campaign item instances or change encounter snapshots; those are the next
integration step.

## Supported rules

- Unarmored AC: 10 + Dexterity modifier.
- Light armor: listed AC + full Dexterity modifier.
- Medium armor: listed AC + Dexterity modifier, maximum +2.
- Heavy armor: listed AC without Dexterity modifier.
- Shield: +2 AC, independent of body armor.
- Strength requirements and Stealth-disadvantage properties are returned as
  explicit derived flags for application-layer enforcement.

The catalogue includes padded, leather, studded leather, hide, chain shirt,
scale mail, breastplate, half plate, ring mail, chain mail, splint, plate and
shield.

## Deliberate boundary

This is rules-engine data/calculation only. Equipment ownership, armor
proficiency enforcement, active-encounter AC refresh and item-to-catalogue
references are not introduced here. The rules engine remains deterministic
and has no persistence or provider dependencies.
