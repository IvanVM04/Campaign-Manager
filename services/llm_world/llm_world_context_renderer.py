"""Render a selected world projection for LLM extraction prompts."""

import json

from models.turn_context import TurnContext
from models.world_context_projection import WorldContextProjection
from models.world_visibility_policy import WorldVisibilityPolicy


class LLMWorldContextRenderer:
    """Convert a turn context or bounded projection into prompt-ready sections."""

    @staticmethod
    def build_context(
        context: TurnContext,
        projection: WorldContextProjection | None = None,
    ) -> dict[str, str]:
        """Render known world records without changing the source snapshot."""
        if projection is not None and not isinstance(
            projection,
            WorldContextProjection,
        ):
            raise TypeError("projection must be a WorldContextProjection or None")
        world = projection.world if projection is not None else context.world

        # ------------------------------------------------------------
        # ENTIDADES CONOCIDAS
        # ------------------------------------------------------------

        entity_lines = []

        for entity_id, entity in world.entities.items():
            marker = ""

            if (
                context.active_character is not None
                and entity_id == context.active_character.entity_id
            ):
                marker = " [PERSONAJE ACTIVO]"
            if (
                context.campaign.current_location_id is not None
                and entity_id == context.campaign.current_location_id
            ):
                marker += " [UBICACIÓN ACTUAL]"

            entity_line = (
                f"- ID {entity_id}: "
                f"{entity.name} "
                f"({entity.entity_type})"
                f"{marker}"
            )
            if entity.aliases:
                entity_line += (
                    " | alias explícitos="
                    + json.dumps(entity.aliases, ensure_ascii=False)
                )
            if entity.description:
                entity_line += (
                    " | descripción conocida="
                    + json.dumps(entity.description, ensure_ascii=False)
                )
            if entity.notes:
                entity_line += (
                    " | notas conocidas="
                    + json.dumps(entity.notes, ensure_ascii=False)
                )
            entity_lines.append(entity_line)

        known_entities = (
            "\n".join(entity_lines)
            if entity_lines
            else "- Ninguna"
        )
        reference_guidance = ""
        if (
            projection is not None
            and projection.diagnostics.reference_status == "ambiguous"
        ):
            reference_guidance = (
                "La referencia a una entidad coincide con varios registros. "
                "No elijas uno al azar, no actualices ninguno y no crees un "
                "duplicado para resolver la ambigüedad. Devuelve operaciones "
                "vacías para esa referencia hasta disponer de aclaración."
            )

        # ------------------------------------------------------------
        # ITEMS CONOCIDOS
        # ------------------------------------------------------------

        item_lines = []

        for item_id, item in world.items.items():
            item_lines.append(
                f"- ID {item_id}: "
                f"{item.name} "
                f"(descripción={json.dumps(item.description, ensure_ascii=False)}, "
                f"importancia={json.dumps(item.significance, ensure_ascii=False)}, "
                f"notas={json.dumps(item.notes, ensure_ascii=False)}, "
                f"único={item.unique}, weapon_key={item.weapon_key}, "
                f"armor_key={item.armor_key}, equipment_slot={item.equipment_slot})"
            )

        known_items = (
            "\n".join(item_lines)
            if item_lines
            else "- Ninguno"
        )

        # ------------------------------------------------------------
        # INSTANCIAS FÍSICAS CONOCIDAS
        # ------------------------------------------------------------

        item_instance_lines = []

        for instance_id, instance in world.item_instances.items():
            item = world.items.get(instance.item_id)

            item_name = (
                item.name
                if item is not None
                else f"Item {instance.item_id}"
            )

            item_instance_lines.append(
                f"- ID {instance_id}: "
                f"{item_name} "
                f"(item_id={instance.item_id}, "
                f"instance_number={instance.instance_number}, "
                f"owner_id={instance.owner_id}, "
                f"location_id={instance.location_id}, "
                f"condition={json.dumps(instance.condition, ensure_ascii=False)}, "
                f"notes={json.dumps(instance.notes, ensure_ascii=False)}, "
                f"active={instance.active})"
            )

        known_item_instances = (
            "\n".join(item_instance_lines)
            if item_instance_lines
            else "- Ninguna"
        )

        # ------------------------------------------------------------
        # RECURSOS CONOCIDOS
        # ------------------------------------------------------------

        resource_lines = []

        for resource_id, resource in world.resources.items():
            resource_lines.append(
                f"- ID {resource_id}: "
                f"{resource.name} "
                f"(tipo={resource.resource_type}, "
                f"unidad={resource.unit}, "
                f"notas={json.dumps(resource.notes, ensure_ascii=False)})"
            )

        known_resources = (
            "\n".join(resource_lines)
            if resource_lines
            else "- Ninguno"
        )

        # ------------------------------------------------------------
        # SALDOS DE RECURSOS
        # ------------------------------------------------------------

        resource_balance_lines = []

        for balance_id, balance in world.resource_balances.items():
            resource = world.resources.get(balance.resource_id)
            owner = world.entities.get(balance.owner_id)
            resource_name = (
                resource.name
                if resource is not None
                else f"Recurso {balance.resource_id}"
            )
            owner_name = (
                owner.name
                if owner is not None
                else f"Entidad {balance.owner_id}"
            )
            unit = resource.unit if resource is not None else ""
            resource_balance_lines.append(
                f"- ID {balance_id}: "
                f"{balance.amount} {unit} de {resource_name} "
                f"(resource_id={balance.resource_id}, "
                f"owner_id={balance.owner_id}, owner={owner_name}, "
                f"notas={json.dumps(balance.notes, ensure_ascii=False)})"
            )

        known_resource_balances = (
            "\n".join(resource_balance_lines)
            if resource_balance_lines
            else "- Ninguno"
        )

        # ------------------------------------------------------------
        # RELACIONES CONOCIDAS
        # ------------------------------------------------------------

        relation_lines = []

        for relation_id, relation in world.relations.items():
            subject = world.entities.get(relation.subject_id)
            target = world.entities.get(relation.target_id)

            subject_name = (
                subject.name
                if subject is not None
                else f"Entidad {relation.subject_id}"
            )
            target_name = (
                target.name
                if target is not None
                else f"Entidad {relation.target_id}"
            )

            relation_lines.append(
                f"- ID {relation_id}: "
                f"{subject_name} "
                f"(ID {relation.subject_id}) "
                f"--[{relation.relation_type}]--> "
                f"{target_name} "
                f"(ID {relation.target_id}), "
                f"active={relation.active}, "
                "metadata="
                + json.dumps(
                    relation.metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )

        known_relations = (
            "\n".join(relation_lines)
            if relation_lines
            else "- Ninguna"
        )

        # ------------------------------------------------------------
        # EVENTOS CONOCIDOS
        # ------------------------------------------------------------

        event_lines = []
        character_entity_id = (
            context.active_character.entity_id
            if context.active_character is not None
            else None
        )
        visible_event_ids = {
            event.id
            for event in WorldVisibilityPolicy.player_visible_events(
                world.events.values(),
                character_entity_id=character_entity_id,
            )
        }
        superseded_event_ids = WorldVisibilityPolicy.superseded_event_ids(
            world.events.values()
        )

        for event_id, event in world.events.items():
            if event_id not in visible_event_ids:
                continue
            temporal_status = (
                "historical/superseded"
                if event_id in superseded_event_ids
                else "current"
            )
            event_lines.append(
                f"- ID {event_id}: "
                f"epistemic_status={event.epistemic_status}, "
                f"provenance_source={event.provenance_source}, "
                f"visibility_scope={event.visibility_scope}, "
                f"source_entity_id={event.source_entity_id}, "
                f"campaign_elapsed_minutes={event.campaign_elapsed_minutes}, "
                f"temporal_status={temporal_status}, "
                f"supersedes_event_id={event.supersedes_event_id}, "
                f"type={event.event_type}, "
                f"title={event.title}, "
                f"description={event.description}, "
                f"consequences={event.consequences}, "
                f"session_id={event.session_id}, "
                "metadata="
                + json.dumps(
                    event.metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )

        known_events = (
            "\n".join(event_lines)
            if event_lines
            else "- Ninguno"
        )

        # ------------------------------------------------------------
        # CAMPAÑA Y SESIÓN ACTUALES
        # ------------------------------------------------------------

        campaign = context.campaign
        campaign_lines = [
            f"Nombre: {campaign.name or 'Sin nombre'}",
            f"Sistema: {campaign.system}",
            f"Tono: {campaign.tone or 'No definido'}",
            f"Ubicación actual (entity ID): {campaign.current_location_id}",
        ]
        if campaign.summary:
            campaign_lines.append(f"Resumen: {campaign.summary}")
        campaign_block = "\n".join(campaign_lines)

        session = context.current_session
        if session is None:
            session_block = "No hay sesión activa."
        else:
            session_lines = [
                f"Número: {session.number}",
                f"Título: {session.title or 'Sin título'}",
                f"Ubicación inicial: {session.start_location or 'No definida'}",
                f"Ubicación final registrada: {session.end_location or 'No definida'}",
            ]
            if session.summary:
                session_lines.append(f"Resumen: {session.summary}")
            session_block = "\n".join(session_lines)

        # ------------------------------------------------------------
        # PERSONAJE ACTIVO
        # ------------------------------------------------------------

        conditions = context.active_character_conditions
        active_conditions = sorted(
            condition.value for condition in conditions.conditions
        )
        conditions_block = (
            "Condiciones: "
            + (", ".join(active_conditions) if active_conditions else "ninguna")
            + f"\nAgotamiento: {conditions.exhaustion_level}"
        )

        active_character = context.active_character

        if active_character is None:
            character_block = "No hay personaje activo."
        else:
            character_block = (
                f"ID de entidad: {active_character.entity_id}\n"
                f"Nivel: {active_character.level}\n"
                f"Clase: {active_character.class_name}\n"
                f"HP actual: {active_character.current_hp}\n"
                f"HP máximo: {active_character.max_hp}\n"
                f"CA: {active_character.armor_class}\n"
                f"FUE: {active_character.strength}\n"
                f"DES: {active_character.dexterity}\n"
                f"CON: {active_character.constitution}\n"
                f"INT: {active_character.intelligence}\n"
                f"SAB: {active_character.wisdom}\n"
                f"CAR: {active_character.charisma}\n"
                f"Competencia: {active_character.proficiency_bonus}"
            )

        return {
            "campaign_block": campaign_block,
            "session_block": session_block,
            "character_block": character_block,
            "conditions_block": conditions_block,
            "known_entities": known_entities,
            "reference_guidance": reference_guidance,
            "known_items": known_items,
            "known_item_instances": known_item_instances,
            "known_resources": known_resources,
            "known_resource_balances": known_resource_balances,
            "known_relations": known_relations,
            "known_events": known_events,
        }
