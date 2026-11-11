"""Single source of truth for structured LLM operation contracts."""

from __future__ import annotations

import json
from dataclasses import MISSING, dataclass, fields
from types import MappingProxyType, UnionType
from typing import Any, Mapping, Union, get_args, get_origin, get_type_hints

from operations.character_operations import (
    ChangeCharacterHpOperation,
    CharacterOperation,
)
from operations.operation_reference import OperationReference
from operations.world_operations import (
    CreateEntityOperation,
    CreateEventOperation,
    CreateItemInstanceOperation,
    CreateItemOperation,
    CreateRelationOperation,
    CreateResourceOperation,
    GainResourceOperation,
    RemoveRelationOperation,
    SpendResourceOperation,
    TransferItemOperation,
    TransferResourceOperation,
    UpdateEntityOperation,
    UpdateItemInstanceOperation,
    UpdateRelationOperation,
)

_FIELD_DESCRIPTIONS: dict[str, str] = {
    "name": "Nombre visible del registro.",
    "entity_type": "Categoría de la entidad.",
    "description": "Descripción conocida y observable.",
    "notes": "Notas de contexto no mecánicas.",
    "active": "Indica si el registro o relación sigue activo.",
    "entity_id": "ID de la entidad que se modifica.",
    "significance": "Importancia narrativa del objeto.",
    "unique": "Indica si la definición es única.",
    "weapon_key": "Clave de arma reconocida por el motor.",
    "armor_key": "Clave de armadura reconocida por el motor.",
    "equipment_slot": "Espacio de equipamiento del objeto.",
    "instance_id": "ID de la instancia física del objeto.",
    "instance_number": "Número de instancia dentro de su definición.",
    "item_id": "ID de la definición del objeto.",
    "owner_id": "ID de la entidad propietaria.",
    "location_id": "ID de la entidad que representa su ubicación.",
    "condition": "Estado descriptivo de la instancia.",
    "new_owner_id": "ID de la nueva entidad propietaria.",
    "resource_id": "ID de la definición del recurso.",
    "resource_type": "Categoría del recurso cuantificable.",
    "unit": "Unidad usada para expresar el recurso.",
    "amount": "Cantidad del recurso que se transfiere o ajusta.",
    "subject_id": "ID de la entidad que inicia la relación o transferencia.",
    "target_id": "ID de la entidad destino.",
    "relation_id": "Identificador estable de la relación.",
    "relation_type": "Tipo semántico de relación.",
    "metadata": "Datos estructurados adicionales del registro.",
    "event_id": "Identificador estable del evento.",
    "event_type": "Categoría histórica del evento.",
    "title": "Título breve del evento.",
    "consequences": "Consecuencias narrativas conocidas del evento.",
    "session_id": "ID de la sesión en la que ocurrió.",
    "secret": "Marca eventos que no deben exponerse como contexto público.",
}


@dataclass(frozen=True, slots=True)
class OperationMetadata:
    """Typed metadata shared by parsing, prompt generation and trust checks."""

    name: str
    operation_class: type[Any]
    description: str
    model_proposable: bool
    reference_fields: tuple[str, ...]
    example: Mapping[str, Any]

    @property
    def dataclass_fields(self) -> tuple[Any, ...]:
        return tuple(fields(self.operation_class))

    @property
    def required_fields(self) -> tuple[str, ...]:
        return tuple(
            field.name
            for field in self.dataclass_fields
            if field.default is MISSING and field.default_factory is MISSING
        )

    def json_schema(self) -> dict[str, Any]:
        hints = get_type_hints(self.operation_class)
        properties: dict[str, Any] = {
            "type": {
                "const": self.name,
                "description": "Tipo exacto de operación.",
            }
        }
        for field in self.dataclass_fields:
            schema = _annotation_schema(hints.get(field.name, Any))
            schema["description"] = _FIELD_DESCRIPTIONS.get(
                field.name, f"Valor de {field.name}."
            )
            properties[field.name] = schema
        return {
            "type": "object",
            "description": self.description,
            "properties": properties,
            "required": ["type", *self.required_fields],
            "additionalProperties": False,
            "examples": [dict(self.example)],
        }


def _annotation_schema(annotation: Any) -> dict[str, Any]:
    """Convert supported dataclass annotations into conservative JSON Schema."""
    if annotation is Any:
        return {"type": "object"}
    if annotation is object:
        # object marks the parser's private omitted-field sentinel.
        return {}
    if annotation is OperationReference:
        return {
            "type": "string",
            "pattern": r"^\$.+",
            "description": "Referencia a un ID creado antes, con formato $nombre.",
        }
    if annotation is str:
        return {"type": "string"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is type(None):
        return {"type": "null"}
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        options = [
            _annotation_schema(option)
            for option in get_args(annotation)
            if option is not object
        ]
        return options[0] if len(options) == 1 else {"anyOf": options}
    if origin is dict:
        return {"type": "object"}
    if origin is list:
        return {"type": "array"}
    return {}


def _description(operation_class: type[Any]) -> str:
    raw = operation_class.__doc__ or operation_class.__name__
    return " ".join(raw.strip().split("\n\n", maxsplit=1)[0].split())


def _metadata(
    name: str,
    operation_class: type[Any],
    *,
    reference_fields: tuple[str, ...] = (),
    example: dict[str, Any],
    model_proposable: bool,
) -> OperationMetadata:
    if model_proposable and issubclass(operation_class, CharacterOperation):
        raise ValueError(
            f"Character operation {name!r} cannot be model-proposable"
        )
    declared_fields = {field.name for field in fields(operation_class)}
    unknown_references = set(reference_fields) - declared_fields
    if unknown_references:
        raise ValueError(
            f"Unknown reference fields for {name}: "
            + ", ".join(sorted(unknown_references))
        )
    return OperationMetadata(
        name=name,
        operation_class=operation_class,
        description=_description(operation_class),
        model_proposable=model_proposable,
        reference_fields=reference_fields,
        example=MappingProxyType(dict(example)),
    )


class OperationMetadataRegistry:
    """Immutable operation catalog used across the structured proposal path."""

    def __init__(self, operations: tuple[OperationMetadata, ...]) -> None:
        by_name = {operation.name: operation for operation in operations}
        if len(by_name) != len(operations):
            raise ValueError("Operation names must be unique")
        self._by_name = MappingProxyType(dict(sorted(by_name.items())))

    @property
    def operations(self) -> tuple[OperationMetadata, ...]:
        return tuple(self._by_name.values())

    @property
    def builders(self) -> dict[str, type[Any]]:
        return {
            name: metadata.operation_class
            for name, metadata in self._by_name.items()
        }

    def get(self, name: str) -> OperationMetadata | None:
        return self._by_name.get(name)

    def model_proposable_operation_types(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, metadata in self._by_name.items()
            if metadata.model_proposable
        )

    def is_model_proposable(self, name: str) -> bool:
        metadata = self.get(name)
        return metadata is not None and metadata.model_proposable

    def render_prompt_contract(
        self, operation_types: tuple[str, ...] | None = None
    ) -> str:
        """Return a compact JSON Schema with descriptions and examples."""
        selected_names = (
            self.model_proposable_operation_types()
            if operation_types is None
            else tuple(dict.fromkeys(operation_types))
        )
        selected: list[dict[str, Any]] = []
        for name in selected_names:
            metadata = self.get(name)
            if metadata is None or not metadata.model_proposable:
                raise ValueError(
                    f"Operation {name!r} is not available for model proposals"
                )
            selected.append(metadata.json_schema())
        schema = {
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "items": {"oneOf": selected},
                    "description": "Operaciones propuestas en orden de resolución.",
                }
            },
            "required": ["operations"],
            "additionalProperties": False,
        }
        return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


DEFAULT_OPERATION_REGISTRY = OperationMetadataRegistry(
    (
        _metadata("create_entity", CreateEntityOperation,
                  example={"type": "create_entity", "name": "Guardia del mercado"},
                  model_proposable=True),
        _metadata("update_entity", UpdateEntityOperation,
                  reference_fields=("entity_id",),
                  example={"type": "update_entity", "entity_id": 12,
                           "description": "Tiene una herida reciente."},
                  model_proposable=True),
        _metadata("create_item", CreateItemOperation,
                  example={"type": "create_item", "name": "Llave de hierro"},
                  model_proposable=True),
        _metadata("create_item_instance", CreateItemInstanceOperation,
                  reference_fields=("item_id", "owner_id", "location_id"),
                  example={"type": "create_item_instance", "item_id": 4, "owner_id": 12},
                  model_proposable=True),
        _metadata("update_item_instance", UpdateItemInstanceOperation,
                  reference_fields=("instance_id", "owner_id", "location_id"),
                  example={"type": "update_item_instance", "instance_id": 8,
                           "condition": "dañado"},
                  model_proposable=True),
        _metadata("transfer_item", TransferItemOperation,
                  reference_fields=("instance_id", "new_owner_id"),
                  example={"type": "transfer_item", "instance_id": 8, "new_owner_id": 12},
                  model_proposable=True),
        _metadata("create_resource", CreateResourceOperation,
                  example={"type": "create_resource", "name": "Oro", "unit": "mo"},
                  model_proposable=True),
        _metadata("gain_resource", GainResourceOperation,
                  reference_fields=("resource_id", "owner_id"),
                  example={"type": "gain_resource", "resource_id": 2,
                           "owner_id": 12, "amount": 10},
                  model_proposable=True),
        _metadata("spend_resource", SpendResourceOperation,
                  reference_fields=("resource_id", "owner_id"),
                  example={"type": "spend_resource", "resource_id": 2,
                           "owner_id": 12, "amount": 5},
                  model_proposable=True),
        _metadata("transfer_resource", TransferResourceOperation,
                  reference_fields=("resource_id", "subject_id", "target_id"),
                  example={"type": "transfer_resource", "resource_id": 2,
                           "subject_id": 12, "target_id": 14, "amount": 5},
                  model_proposable=True),
        _metadata("create_relation", CreateRelationOperation,
                  reference_fields=("subject_id", "target_id"),
                  example={"type": "create_relation", "relation_id": "guardia_mercado",
                           "subject_id": 12, "relation_type": "miembro_de", "target_id": 14},
                  model_proposable=True),
        _metadata("update_relation", UpdateRelationOperation,
                  reference_fields=("target_id",),
                  example={"type": "update_relation", "relation_id": "guardia_mercado",
                           "active": False},
                  model_proposable=True),
        _metadata("remove_relation", RemoveRelationOperation,
                  example={"type": "remove_relation", "relation_id": "guardia_mercado"},
                  model_proposable=True),
        _metadata("create_event", CreateEventOperation,
                  reference_fields=("session_id",),
                  example={"type": "create_event", "event_id": "mercader_amenazado",
                           "event_type": "social", "title": "El mercader fue amenazado"},
                  model_proposable=True),
        _metadata("change_character_hp", ChangeCharacterHpOperation,
                  reference_fields=("entity_id",),
                  example={"type": "change_character_hp", "entity_id": 12, "amount": -4},
                  model_proposable=False),
    )
)
