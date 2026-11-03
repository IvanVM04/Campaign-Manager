"""Use cases for campaign-scoped persistent effects."""

from __future__ import annotations

import sqlite3

from database import get_conn
from models.persistent_effect import EffectStatus, PersistentEffect


class PersistentEffectService:
    def __init__(self, *, repository, entity_repository, campaign_id: int) -> None:
        if isinstance(campaign_id, bool) or not isinstance(campaign_id, int) or campaign_id < 1:
            raise ValueError("campaign_id must be a positive integer")
        self.repository = repository
        self.entity_repository = entity_repository
        self.campaign_id = campaign_id

    def create(
        self,
        *,
        entity_id: int,
        effect_type,
        effect_key: str,
        name: str,
        description: str = "",
        source_type="unknown",
        source_entity_id: int | None = None,
        source_reference: str | None = None,
        duration_type="permanent",
        duration_condition: str | None = None,
        level: int | None = None,
    ) -> PersistentEffect:
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
            level=level,
        )
        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if self.entity_repository.get_entity(
                entity_id, campaign_id=self.campaign_id, conn=conn
            ) is None:
                raise LookupError("target entity does not exist in this campaign")
            if source_entity_id is not None and self.entity_repository.get_entity(
                source_entity_id, campaign_id=self.campaign_id, conn=conn
            ) is None:
                raise LookupError("source entity does not exist in this campaign")
            try:
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
        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = self.repository.get(
                effect_id, campaign_id=self.campaign_id, conn=conn
            )
            if current is None:
                raise LookupError("effect does not exist in this campaign")
            if current.status is EffectStatus.REMOVED and target_status is not EffectStatus.REMOVED:
                raise ValueError("removed effects are terminal and cannot be reactivated")
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
