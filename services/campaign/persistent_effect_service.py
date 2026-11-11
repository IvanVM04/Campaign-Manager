"""Use cases for campaign-scoped persistent effects."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

from database import transaction
from models.persistent_effect import (
    EffectDurationType,
    EffectSourceType,
    EffectStatus,
    PersistentEffect,
)
from repositories.campaign_clock_repository import CampaignClockRepository


class PersistentEffectService:
    def __init__(self, *, repository, entity_repository, campaign_id: int, clock_repository=None, encounter_repository=None) -> None:
        if isinstance(campaign_id, bool) or not isinstance(campaign_id, int) or campaign_id < 1:
            raise ValueError("campaign_id must be a positive integer")
        self.repository = repository
        self.entity_repository = entity_repository
        self.campaign_id = campaign_id
        self.clock_repository = clock_repository or CampaignClockRepository()
        self.encounter_repository = encounter_repository

    def create(
        self,
        *,
        entity_id: int,
        effect_type,
        effect_key: str,
        name: str,
        description: str = "",
        source_type: EffectSourceType | str = EffectSourceType.UNKNOWN,
        source_entity_id: int | None = None,
        source_reference: str | None = None,
        duration_type: EffectDurationType | str = EffectDurationType.PERMANENT,
        duration_condition: str | None = None,
        duration_minutes: int | None = None,
        encounter_id: str | None = None,
        duration_rounds: int | None = None,
        duration_turns: int | None = None,
        level: int | None = None,
    ) -> PersistentEffect:
        source_type = EffectSourceType(source_type)
        duration_type = EffectDurationType(duration_type)
        effect = PersistentEffect(
            campaign_id=self.campaign_id,
            entity_id=entity_id,
            effect_type=effect_type,
            effect_key=effect_key,
            name=name,
            description=description,
            source_type=source_type,
            source_entity_id=source_entity_id,
            source_reference=source_reference,
            duration_type=duration_type,
            duration_condition=duration_condition,
            duration_minutes=duration_minutes,
            expires_at_minute=(1 if EffectDurationType(duration_type) is EffectDurationType.CAMPAIGN_TIME else None),
            encounter_id=encounter_id,
            duration_rounds=duration_rounds,
            expires_at_round=(1 if EffectDurationType(duration_type) is EffectDurationType.ENCOUNTER_ROUNDS else None),
            duration_turns=duration_turns,
            expires_at_turn=(1 if EffectDurationType(duration_type) is EffectDurationType.ENCOUNTER_TURNS else None),
            level=level,
        )
        with transaction("IMMEDIATE") as conn:
            if self.entity_repository.get_entity(
                entity_id, campaign_id=self.campaign_id, conn=conn
            ) is None:
                raise LookupError("target entity does not exist in this campaign")
            if source_entity_id is not None and self.entity_repository.get_entity(
                source_entity_id, campaign_id=self.campaign_id, conn=conn
            ) is None:
                raise LookupError("source entity does not exist in this campaign")
            try:
                if effect.duration_type is EffectDurationType.CAMPAIGN_TIME:
                    clock = self.clock_repository.ensure(self.campaign_id, conn=conn)
                    duration_minutes = effect.duration_minutes
                    if duration_minutes is None:
                        raise ValueError("campaign-time effects require duration_minutes")
                    effect = replace(
                        effect,
                        expires_at_minute=clock.elapsed_minutes + duration_minutes,
                    )
                elif effect.duration_type in (EffectDurationType.ENCOUNTER_ROUNDS, EffectDurationType.ENCOUNTER_TURNS):
                    if self.encounter_repository is None:
                        raise ValueError("encounter-scoped durations are unavailable")
                    encounter = self.encounter_repository.get(
                        effect.encounter_id, campaign_id=self.campaign_id, conn=conn
                    )
                    if encounter is None or encounter.status.value != "active":
                        raise LookupError("duration encounter must be active in this campaign")
                    participant = next(
                        (item for item in encounter.combatants.values() if item.entity_id == entity_id),
                        None,
                    )
                    if participant is None:
                        raise ValueError("effect target must participate in the duration encounter")
                    if effect.duration_type is EffectDurationType.ENCOUNTER_ROUNDS:
                        effect = replace(
                            effect,
                            expires_at_round=encounter.round_number + effect.duration_rounds,
                        )
                    else:
                        absolute_turn = (
                            (encounter.round_number - 1) * len(encounter.initiative_order)
                            + encounter.turn_index
                        )
                        effect = replace(effect, expires_at_turn=absolute_turn + effect.duration_turns)
                return self.repository.create(effect, conn=conn)
            except sqlite3.IntegrityError as exc:
                raise ValueError(str(exc)) from exc

    def list_for_entity(
        self,
        entity_id: int,
        *,
        include_removed: bool = False,
    ) -> list[PersistentEffect]:
        if self.entity_repository.get_entity(
            entity_id, campaign_id=self.campaign_id
        ) is None:
            raise LookupError("target entity does not exist in this campaign")
        return self.repository.list_for_entity(
            entity_id,
            campaign_id=self.campaign_id,
            include_removed=include_removed,
        )

    def set_status(self, effect_id: str, status: EffectStatus | str) -> PersistentEffect:
        target_status = EffectStatus(status)
        if target_status is EffectStatus.EXPIRED:
            raise ValueError("effect expiration is managed by the campaign clock")
        with transaction("IMMEDIATE") as conn:
            current = self.repository.get(
                effect_id, campaign_id=self.campaign_id, conn=conn
            )
            if current is None:
                raise LookupError("effect does not exist in this campaign")
            if current.status in (EffectStatus.REMOVED, EffectStatus.EXPIRED) and target_status is not EffectStatus.REMOVED:
                raise ValueError("inactive effects are terminal and cannot be reactivated")
            if current.status is EffectStatus.EXPIRED:
                return current
            if current.status is target_status:
                return current
            self.repository.update_status(
                effect_id,
                campaign_id=self.campaign_id,
                status=target_status,
                conn=conn,
            )
            updated = self.repository.get(
                effect_id, campaign_id=self.campaign_id, conn=conn
            )
            if updated is None:
                raise RuntimeError("effect disappeared while updating its status")
            return updated

    def remove(self, effect_id: str) -> PersistentEffect:
        return self.set_status(effect_id, EffectStatus.REMOVED)
