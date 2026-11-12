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
    item_name: str | None
    instance_number: int
    owner_id: int | None
    owner_name: str | None
    location_id: int | None
    location_name: str | None
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
    resource_name: str | None
    owner_id: int
    owner_name: str | None
    amount: float
    notes: str


class WorldRelationRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    subject_id: int
    subject_name: str | None
    relation_type: str
    target_id: int
    target_name: str | None
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
    epistemic_status: str = "confirmed"
    provenance_source: str = "gm_authored"
    visibility_scope: str = "public"
    source_entity_id: int | None = None
    source_entity_name: str | None = None
    campaign_elapsed_minutes: int | None = None
    supersedes_event_id: str | None = None
    is_current: bool = True


WorldCollectionItemRead = (
    WorldItemRead
    | WorldItemInstanceRead
    | WorldResourceRead
    | WorldResourceBalanceRead
    | WorldRelationRead
    | WorldEventRead
)


class WorldCollectionPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[WorldCollectionItemRead, ...]
    total: int
    limit: int
    offset: int
