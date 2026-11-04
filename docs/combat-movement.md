# Combat movement and opportunity attacks

The D&D 5e (2014) movement rules are implemented as pure functions in
`rules_engine.dnd5e_2014.combat.movement`.

- Tactical distance uses a 5-foot square grid; diagonal squares cost 5 feet.
- Movement paths must consist of adjacent squares.
- Base speed is reduced by conditions that set speed to zero and by exhaustion
  levels 2–4 (half speed); exhaustion level 5 sets speed to zero.
- An opportunity attack is eligible when voluntary movement leaves an
  attacker's reach. Forced movement, teleportation, Disengage, an incapacitated
  or dead attacker, and an unavailable reaction suppress eligibility.
- The rules helper does not consume a reaction or roll an attack. Those are
  encounter/application responsibilities. It also does not determine
  visibility, cover, occupied squares, difficult terrain, or creature-specific
  reach; callers must provide the relevant state.

This is the deterministic rules foundation. Encounter position persistence,
movement API orchestration, and the actual reaction attack transaction are
separate integration work and must use these helpers rather than duplicating
the rules in API routes.
