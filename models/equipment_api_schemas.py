"""Transport schemas for campaign character equipment."""

from typing import Literal

from pydantic import BaseModel, Field, StrictInt

EquipmentSlot = Literal[
    "main_hand", "off_hand", "body", "head", "hands", "feet",
    "cloak", "neck", "ring_1", "ring_2", "waist", "wondrous",
    "ammunition",
]


class EquipItemIn(BaseModel):
    item_instance_id: StrictInt = Field(gt=0)
    slot: EquipmentSlot
