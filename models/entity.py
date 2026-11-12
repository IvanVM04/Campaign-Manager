from dataclasses import dataclass, field

MAX_ENTITY_ALIASES = 20
MAX_ENTITY_ALIAS_LENGTH = 100


def normalize_entity_aliases(
    aliases: list[str] | tuple[str, ...],
    *,
    canonical_name: str = "",
) -> list[str]:
    """Validate and normalize explicit, durable alternate names for an entity."""
    if not isinstance(aliases, (list, tuple)):
        raise TypeError("entity aliases must be a list or tuple")
    if len(aliases) > MAX_ENTITY_ALIASES:
        raise ValueError(f"an entity may have at most {MAX_ENTITY_ALIASES} aliases")
    canonical = canonical_name.strip().casefold()
    normalized: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        if not isinstance(alias, str):
            raise TypeError("entity aliases must contain only strings")
        value = alias.strip()
        if not value:
            raise ValueError("entity aliases cannot be blank")
        if len(value) > MAX_ENTITY_ALIAS_LENGTH:
            raise ValueError(
                f"entity aliases must be at most {MAX_ENTITY_ALIAS_LENGTH} characters"
            )
        key = value.casefold()
        if key == canonical or key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


@dataclass
class Entity:
    """Persistent campaign-world entity: character, item, place, faction, creature, etc."""

    id: int | None = None
    name: str = ""
    entity_type: str = ""
    description: str = ""
    notes: str = ""
    active: bool = True
    aliases: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.aliases = normalize_entity_aliases(
            self.aliases,
            canonical_name=self.name,
        )
