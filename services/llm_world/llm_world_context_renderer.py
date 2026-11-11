"""Render a selected world projection for LLM extraction prompts."""

from models.turn_context import TurnContext
from models.world_context_projection import WorldContextProjection


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

            entity_lines.append(
                f"- ID {entity_id}: "
                f"{entity.name} "
                f"({entity.entity_type})"
                f"{marker}"
            )

        known_entities = (
            "\n".join(entity_lines)
            if entity_lines
            else "- Ninguna"
        )

        # ------------------------------------------------------------
        # ITEMS CONOCIDOS
        # ------------------------------------------------------------

        item_lines = []

        for item_id, item in world.items.items():
            item_lines.append(
                f"- ID {item_id}: "
                f"{item.name} "
                f"(weapon_key={item.weapon_key}, armor_key={item.armor_key}, "
                f"equipment_slot={item.equipment_slot})"
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
                f"condition={instance.condition}, "
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
                f"unidad={resource.unit})"
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
                f"owner_id={balance.owner_id}, owner={owner_name})"
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
                f"metadata={relation.metadata}"
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

        for event_id, event in world.events.items():
            if event.secret:
                continue
            event_lines.append(
                f"- ID {event_id}: "
                f"type={event.event_type}, "
                f"title={event.title}, "
                f"description={event.description}, "
                f"consequences={event.consequences}, "
                f"session_id={event.session_id}, "
                f"secret={event.secret}, "
                f"metadata={event.metadata}"
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
            "known_entities": known_entities,
            "known_items": known_items,
            "known_item_instances": known_item_instances,
            "known_resources": known_resources,
            "known_resource_balances": known_resource_balances,
            "known_relations": known_relations,
            "known_events": known_events,
        }
