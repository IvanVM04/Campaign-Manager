
from pydantic import BaseModel, Field, field_validator


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    system: str = Field(default="D&D 5e 2014", min_length=1, max_length=100)
    tone: str = Field(default="", max_length=100)
    summary: str = Field(default="", max_length=5000)

    @field_validator("name", "system")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value


class CampaignUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        max_length=200,
    )
    system: str | None = Field(
        default=None,
        max_length=100,
    )
    tone: str | None = Field(
        default=None,
        max_length=100,
    )
    summary: str | None = Field(
        default=None,
        max_length=5000,
    )

    @field_validator("name", "system")
    @classmethod
    def validate_optional_required_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")

        return value

    @field_validator("tone", "summary")
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        return value.strip() if value is not None else None


class CampaignSessionUpdate(BaseModel):
    session_id: int | None = None


class SessionIn(BaseModel):
    number: int = Field(
        ...,
        ge=1,
    )
    title: str = Field(
        default="",
        max_length=200,
    )
    summary: str = Field(
        default="",
        max_length=5000,
    )
    start_location: str = Field(
        default="",
        max_length=200,
    )
    end_location: str = Field(
        default="",
        max_length=200,
    )
    notes: str = Field(
        default="",
        max_length=5000,
    )


class TurnIn(BaseModel):
    player_input: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )

    @field_validator("player_input")
    @classmethod
    def validate_player_input(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "player_input must not be empty"
            )

        return value


class ActiveCharacterUpdate(BaseModel):
    character_id: int | None = Field(
        default=None,
        ge=1,
    )


class SillyTavernContextIn(BaseModel):
    """
    Petición de contexto procedente de SillyTavern.

    query representa la acción o situación actual que el
    modelo va a utilizar para determinar qué recuerdos del
    mundo son relevantes.
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )

    @field_validator("query")
    @classmethod
    def validate_query(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "query must not be empty"
            )

        return value


class SillyTavernTurnIn(BaseModel):
    """
    Turno ya generado por SillyTavern.

    Campaign Manager NO genera la narrativa en este endpoint.
    Recibe la acción del jugador y la narrativa resultante,
    extrae los cambios persistentes y los aplica al mundo.
    """

    player_input: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )

    narrative: str = Field(
        ...,
        min_length=1,
        max_length=30000,
    )

    external_turn_id: str | None = Field(
        default=None,
        max_length=500,
    )

    turn_version: int = Field(
        default=1,
        ge=1,
    )

    @field_validator(
        "player_input",
        "narrative",
    )
    @classmethod
    def validate_text(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "text must not be empty"
            )

        return value

    @field_validator("external_turn_id")
    @classmethod
    def validate_external_turn_id(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "external_turn_id must not be empty"
            )

        return value


class CharacterCreate(BaseModel):
    """
    Datos mínimos necesarios para crear el personaje jugador.

    No pretende ser todavía un character builder completo de D&D.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    class_name: str | None = Field(
        default=None,
        max_length=100,
    )

    level: int = Field(
        default=1,
        ge=1,
        le=20,
    )

    max_hp: int = Field(
        ...,
        ge=1,
        le=1000,
    )

    current_hp: int | None = Field(
        default=None,
        ge=0,
        le=1000,
    )

    armor_class: int = Field(
        default=10,
        ge=0,
        le=100,
    )

    strength: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    dexterity: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    constitution: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    intelligence: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    wisdom: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    charisma: int = Field(
        default=10,
        ge=1,
        le=30,
    )

    proficiency_bonus: int = Field(
        default=2,
        ge=2,
        le=6,
    )

    skill_proficiencies: list[str] = Field(default_factory=list)

    skill_expertise: list[str] = Field(default_factory=list)

    saving_throw_proficiencies: list[str] = Field(default_factory=list)

    metadata: dict = Field(
        default_factory=dict,
    )

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "name must not be empty"
            )

        return value

    @field_validator("class_name")
    @classmethod
    def validate_class_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        return value

    @field_validator("current_hp")
    @classmethod
    def validate_current_hp(
        cls,
        value: int | None,
        info,
    ) -> int | None:
        if value is None:
            return value

        max_hp = info.data.get("max_hp")

        if max_hp is not None and value > max_hp:
            raise ValueError(
                "current_hp cannot exceed max_hp"
            )

        return value
