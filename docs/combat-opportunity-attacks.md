# Opportunity attack resolution

The combat API exposes `POST /encounters/{encounter_id}/opportunity-attack` for resolving a D&D 5e (2014) opportunity attack after the active combatant has moved one grid square.

The request identifies the reacting combatant, the active mover, the mover's previous grid coordinate, and the encounter turn token. The mover's persisted current coordinate is treated as the destination. The service verifies that the step leaves the reacting combatant's reach, is voluntary, is not protected by Disengage, and that the reacting combatant is alive, conscious, not incapacitated, and still has its reaction.

Reach is derived from the equipped weapon: 5 feet normally and 10 feet for a weapon with the Reach property. Ranged weapons are rejected. The request cannot grant extra reach. The attack uses the same weapon profile, attack roll, advantage/disadvantage, damage, defenses, HP synchronization, and death-state handling as a normal weapon attack.

The reaction is consumed in the same database transaction as attack resolution and any HP changes. A miss still consumes the reaction. A rejected trigger, invalid request, or failed transaction does not consume it. The attack does not consume the attacker's action.

This increment currently supports persisted player-character attackers with an equipped supported melee weapon. NPC attack profiles, visibility/line-of-sight adjudication, reach-modifying effects, and resolving the attack inside the movement transaction remain out of scope. The caller must invoke the endpoint immediately after the one-square movement event and provide the true previous coordinate; the service checks it against the persisted destination but does not maintain a movement-event ledger.
