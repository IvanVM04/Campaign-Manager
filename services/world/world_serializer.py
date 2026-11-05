from __future__ import annotations

from dataclasses import asdict
from typing import Any


class WorldSerializer:
    """
    Convierte objetos del dominio WorldState en representaciones
    estructuradas serializables.

    No busca información.
    No calcula relevancia.
    No construye contexto textual.
    No modifica objetos del dominio.

    Su única responsabilidad es adaptar objetos del dominio a
    diccionarios públicos.
    """

    @staticmethod
    def serialize(value: Any) -> dict[str, Any]:
        """
        Convierte un objeto dataclass del dominio en un diccionario.
        """

        return asdict(value)

    @staticmethod
    def entity_to_dict(
        entity: Any,
    ) -> dict[str, Any]:
        return WorldSerializer.serialize(entity)

    @staticmethod
    def item_to_dict(
        item: Any,
    ) -> dict[str, Any]:
        return WorldSerializer.serialize(item)

    @staticmethod
    def item_instance_to_dict(
        item_instance: Any,
    ) -> dict[str, Any]:
        return WorldSerializer.serialize(item_instance)

    @staticmethod
    def resource_to_dict(
        resource: Any,
    ) -> dict[str, Any]:
        return WorldSerializer.serialize(resource)

    @staticmethod
    def resource_balance_to_dict(
        resource_balance: Any,
    ) -> dict[str, Any]:
        return WorldSerializer.serialize(resource_balance)

    @staticmethod
    def relation_to_dict(
        relation: Any,
    ) -> dict[str, Any]:
        return WorldSerializer.serialize(relation)

    @staticmethod
    def event_to_dict(
        event: Any,
    ) -> dict[str, Any]:
        return WorldSerializer.serialize(event)