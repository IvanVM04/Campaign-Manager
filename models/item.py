from dataclasses import dataclass


@dataclass
class Item:
    """
    Definición de un tipo de objeto.

    Ejemplo:
        Diamante arcoíris

    Esta clase NO representa una copia física concreta.
    """

    id: int | None = None

    name: str = ""

    description: str = ""

    significance: str = ""

    unique: bool = False

    notes: str = ""

    weapon_key: str | None = None

    equipment_slot: str | None = None

    def __post_init__(self) -> None:
        if self.weapon_key is not None and self.equipment_slot is None:
            self.equipment_slot = "main_hand"
        if self.equipment_slot is not None and self.equipment_slot not in {
            "main_hand", "off_hand", "body", "head", "hands", "feet",
            "cloak", "neck", "ring_1", "ring_2", "waist", "wondrous",
            "ammunition",
        }:
            raise ValueError("unsupported equipment slot")


@dataclass
class ItemInstance:
    """
    Copia física concreta de un Item.

    Ejemplo:

        Item:
            Diamante arcoíris

        Instances:
            #1 -> Fungoso
            #2 -> Templo perdido
    """

    id: int | None = None

    item_id: int = 0

    instance_number: int = 1

    owner_id: int | None = None

    location_id: int | None = None

    condition: str = ""

    notes: str = ""

    active: bool = True