from dataclasses import dataclass, field
from typing import Any

from operations.operation_reference import OperationReference

_UNSET = object()

# ============================================================
# BASE
# ============================================================

@dataclass(frozen=True)
class WorldOperation:
    """
    Operación de dominio que describe un cambio que debe
    realizarse sobre el estado de la campaña.

    Las operaciones concretas contienen los datos
    necesarios para realizar cada cambio.
    """



# ============================================================
# ENTITIES
# ============================================================

@dataclass(frozen=True)
class CreateEntityOperation(WorldOperation):
    """
    Crea una entidad persistente dentro del mundo.

    El ID se genera por WorldApplier.
    El LLM NO debe proporcionar el ID.
    """

    name: str
    entity_type: str = ""
    description: str = ""
    notes: str = ""
    active: bool = True
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UpdateEntityOperation(WorldOperation):
    """
    Modifica únicamente los campos proporcionados de una
    entidad existente.

    None significa "no modificar ese campo".

    entity_id puede utilizar OperationReference para
    referenciar una entidad creada por una operación anterior.
    """

    entity_id: int | OperationReference

    name: str | None = None
    entity_type: str | None = None
    description: str | None = None
    notes: str | None = None
    active: bool | None = None
    aliases: list[str] | None = None


# ============================================================
# ITEMS
# ============================================================

@dataclass(frozen=True)
class CreateItemOperation(WorldOperation):
    """
    Crea la definición de un tipo de objeto.

    Ejemplo:

        Item:
            Espada de hierro

    Esto NO crea una copia física concreta.
    """

    name: str
    description: str = ""
    significance: str = ""
    unique: bool = False
    notes: str = ""
    weapon_key: str | None = None
    armor_key: str | None = None
    equipment_slot: str | None = None


@dataclass(frozen=True)
class TransferItemOperation(WorldOperation):
    """
    Transfiere una instancia física concreta de un objeto
    a otro propietario.

    Los IDs pueden utilizar OperationReference para
    referenciar objetos creados por operaciones anteriores.
    """

    instance_id: int | OperationReference

    new_owner_id: int | OperationReference


@dataclass(frozen=True)
class CreateItemInstanceOperation(WorldOperation):
    """
    Crea una instancia física concreta de un Item existente.

    Los IDs pueden utilizar OperationReference para
    referenciar objetos creados por operaciones anteriores.
    """

    item_id: int | OperationReference

    instance_number: int = 1

    owner_id: int | OperationReference | None = None

    location_id: int | OperationReference | None = None

    condition: str = ""

    notes: str = ""

    active: bool = True

@dataclass(frozen=True)
class UpdateItemInstanceOperation(WorldOperation):
    """
    Modifica únicamente los campos proporcionados de una
    instancia física existente.

    Un campo omitido significa "no modificar".
    None significa establecer explícitamente NULL.
    """

    instance_id: int | OperationReference

    owner_id: int | OperationReference | None | object = _UNSET

    location_id: int | OperationReference | None | object = _UNSET

    condition: str | None | object = _UNSET

    notes: str | None | object = _UNSET

    active: bool | None | object = _UNSET


# ============================================================
# RESOURCES
# ============================================================

@dataclass(frozen=True)
class CreateResourceOperation(WorldOperation):
    """
    Crea un recurso cuantificable de la campaña.

    Ejemplos:

        oro
        reputación
        suministros
        influencia
    """

    name: str
    resource_type: str = "generic"
    unit: str = ""
    notes: str = ""


@dataclass(frozen=True)
class GainResourceOperation(WorldOperation):
    """
    Añade una cantidad de un recurso al balance
    de una entidad.

    Los IDs pueden utilizar OperationReference para
    referenciar objetos creados por operaciones anteriores.
    """

    resource_id: int | OperationReference
    owner_id: int | OperationReference
    amount: float

@dataclass(frozen=True)
class SpendResourceOperation(WorldOperation):
    """
    Reduce una cantidad de un recurso que posee
    una entidad.

    Los IDs pueden utilizar OperationReference para
    referenciar objetos creados por operaciones anteriores.
    """

    resource_id: int | OperationReference
    owner_id: int | OperationReference
    amount: float


@dataclass(frozen=True)
class TransferResourceOperation(WorldOperation):
    """
    Transfiere una cantidad de un recurso desde una entidad
    hacia otra.

    Los IDs pueden utilizar OperationReference para
    referenciar objetos creados por operaciones anteriores.
    """

    resource_id: int | OperationReference
    subject_id: int | OperationReference
    target_id: int | OperationReference
    amount: float


# ============================================================
# RELATIONS
# ============================================================

@dataclass(frozen=True)
class CreateRelationOperation(WorldOperation):
    """
    Crea una relación entre dos entidades existentes.

    Los IDs pueden utilizar OperationReference para
    referenciar entidades creadas por operaciones anteriores.
    """

    relation_id: str
    subject_id: int | OperationReference
    relation_type: str
    target_id: int | OperationReference
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class UpdateRelationOperation(WorldOperation):
    """
    Modifica una relación existente.

    target_id puede utilizar OperationReference para
    referenciar una entidad creada por una operación anterior.
    """

    relation_id: str
    relation_type: str | None = None
    target_id: int | OperationReference | None = None
    metadata: dict[str, Any] | None = None
    active: bool | None = None


@dataclass(frozen=True)
class RemoveRelationOperation(WorldOperation):
    """
    Desactiva una relación existente.
    """

    relation_id: str


# ============================================================
# EVENTS
# ============================================================

@dataclass(frozen=True)
class CreateEventOperation(WorldOperation):
    """
    Crea un evento histórico en el mundo.
    """

    event_id: str

    event_type: str

    title: str

    description: str = ""

    consequences: str = ""

    session_id: int | None = None

    secret: bool = False

    metadata: dict[str, Any] | None = None