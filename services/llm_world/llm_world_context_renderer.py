"""Render the current world snapshot for LLM extraction prompts."""

from models.turn_context import TurnContext


class LLMWorldContextRenderer:
    """Convert the current turn context into prompt-ready world sections."""

    @staticmethod
    def build_context(context: TurnContext) -> dict[str, str]:
        """Render known world records without changing the source snapshot."""
        world = context.world

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
        # RELACIONES CONOCIDAS
        # ------------------------------------------------------------

        relation_lines = []

        for relation_id, relation in world.relations.items():
            subject = world.entities.get(
                relation.subject_id
            )
            target = world.entities.get(
                relation.target_id
            )

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
        # PERSONAJE ACTIVO
        # ------------------------------------------------------------

        active_character = context.active_character

        if active_character is None:
            character_block = (
                "No hay personaje activo."
            )
        else:
            character_block = (
                f"ID de entidad: "
                f"{active_character.entity_id}\n"
                f"Nivel: "
                f"{active_character.level}\n"
                f"Clase: "
                f"{active_character.class_name}\n"
                f"HP actual: "
                f"{active_character.current_hp}\n"
                f"HP máximo: "
                f"{active_character.max_hp}\n"
                f"CA: "
                f"{active_character.armor_class}\n"
                f"FUE: "
                f"{active_character.strength}\n"
                f"DES: "
                f"{active_character.dexterity}\n"
                f"CON: "
                f"{active_character.constitution}\n"
                f"INT: "
                f"{active_character.intelligence}\n"
                f"SAB: "
                f"{active_character.wisdom}\n"
                f"CAR: "
                f"{active_character.charisma}\n"
                f"Competencia: "
                f"{active_character.proficiency_bonus}"
            )

        return {
            "character_block": character_block,
            "known_entities": known_entities,
            "known_items": known_items,
            "known_item_instances": known_item_instances,
            "known_resources": known_resources,
            "known_relations": known_relations,
            "known_events": known_events,
        }
