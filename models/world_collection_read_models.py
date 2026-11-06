from pydantic import BaseModel, ConfigDict


class WorldItemRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None
    name: str
    description: str
    significance: str
    unique: bool
    notes: str
    weapon_key: str | None
    armor_key: str | None
    equipment_slot: str | None


class WorldItemInstanceRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None
    item_id: int
    instance_number: int
    owner_id: int | None
    location_id: int | None
    condition: str
    notes: str
    active: bool


class WorldResourceRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None
    name: str
    resource_type: str
    unit: str
    notes: str


class WorldResourceBalanceRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None
    resource_id: int
    owner_id: int
    amount: float
    notes: str


class WorldRelationRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    subject_id: int
    relation_type: str
    target_id: int
    metadata_json: str | None
    active: bool


class WorldEventRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    event_type: str
    title: str
    description: str
    consequences: str
    session_id: int | None
    secret: bool
    metadata_json: str


class WorldCollectionPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[BaseModel, ...]
    total: int
    limit: int
    offset: int
