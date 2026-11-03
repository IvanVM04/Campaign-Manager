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