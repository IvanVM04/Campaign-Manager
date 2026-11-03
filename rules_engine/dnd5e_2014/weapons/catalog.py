"""SRD 5.1 (2014) weapon mechanics; game rules data only.

Weapon keys are stable identifiers used by campaign items. The catalogue is
immutable application data; physical copies remain ordinary ItemInstances.
"""
from dataclasses import dataclass
from enum import Enum


class WeaponCategory(str, Enum):
    SIMPLE_MELEE = "simple_melee"
    SIMPLE_RANGED = "simple_ranged"
    MARTIAL_MELEE = "martial_melee"
    MARTIAL_RANGED = "martial_ranged"


class WeaponProperty(str, Enum):
    AMMUNITION = "ammunition"
    FINESSE = "finesse"
    HEAVY = "heavy"
    LIGHT = "light"
    LOADING = "loading"
    REACH = "reach"
    SPECIAL = "special"
    THROWN = "thrown"
    TWO_HANDED = "two_handed"
    VERSATILE = "versatile"


@dataclass(frozen=True)
class WeaponDefinition:
    key: str
    name: str
    category: WeaponCategory
    damage_dice: str
    damage_type: str
    properties: frozenset[WeaponProperty] = frozenset()
    normal_range: int | None = None
    long_range: int | None = None
    versatile_damage_dice: str | None = None

    @property
    def is_ranged(self) -> bool:
        return self.category in {
            WeaponCategory.SIMPLE_RANGED,
            WeaponCategory.MARTIAL_RANGED,
        }

    @property
    def is_melee(self) -> bool:
        return not self.is_ranged


def _w(key, name, category, dice, damage, props=(), normal=None, long=None, versatile=None):
    return WeaponDefinition(key, name, category, dice, damage, frozenset(props), normal, long, versatile)


P = WeaponProperty
C = WeaponCategory

_WEAPONS = (
    _w("club", "Club", C.SIMPLE_MELEE, "1d4", "bludgeoning", (P.LIGHT,)),
    _w("dagger", "Dagger", C.SIMPLE_MELEE, "1d4", "piercing", (P.FINESSE, P.LIGHT, P.THROWN), 20, 60),
    _w("greatclub", "Greatclub", C.SIMPLE_MELEE, "1d8", "bludgeoning", (P.TWO_HANDED,)),
    _w("handaxe", "Handaxe", C.SIMPLE_MELEE, "1d6", "slashing", (P.LIGHT, P.THROWN), 20, 60),
    _w("javelin", "Javelin", C.SIMPLE_MELEE, "1d6", "piercing", (P.THROWN,), 30, 120),
    _w("light_hammer", "Light hammer", C.SIMPLE_MELEE, "1d4", "bludgeoning", (P.LIGHT, P.THROWN), 20, 60),
    _w("mace", "Mace", C.SIMPLE_MELEE, "1d6", "bludgeoning"),
    _w("quarterstaff", "Quarterstaff", C.SIMPLE_MELEE, "1d6", "bludgeoning", (P.VERSATILE,), versatile="1d8"),
    _w("sickle", "Sickle", C.SIMPLE_MELEE, "1d4", "slashing", (P.LIGHT,)),
    _w("spear", "Spear", C.SIMPLE_MELEE, "1d6", "piercing", (P.THROWN, P.VERSATILE), 20, 60, "1d8"),
    _w("light_crossbow", "Light crossbow", C.SIMPLE_RANGED, "1d8", "piercing", (P.AMMUNITION, P.LOADING, P.TWO_HANDED), 80, 320),
    _w("dart", "Dart", C.SIMPLE_RANGED, "1d4", "piercing", (P.FINESSE, P.THROWN), 20, 60),
    _w("shortbow", "Shortbow", C.SIMPLE_RANGED, "1d6", "piercing", (P.AMMUNITION, P.TWO_HANDED), 80, 320),
    _w("sling", "Sling", C.SIMPLE_RANGED, "1d4", "bludgeoning", (P.AMMUNITION,), 30, 120),
    _w("battleaxe", "Battleaxe", C.MARTIAL_MELEE, "1d8", "slashing", (P.VERSATILE,), versatile="1d10"),
    _w("flail", "Flail", C.MARTIAL_MELEE, "1d8", "bludgeoning"),
    _w("glaive", "Glaive", C.MARTIAL_MELEE, "1d10", "slashing", (P.HEAVY, P.REACH, P.TWO_HANDED)),
    _w("greataxe", "Greataxe", C.MARTIAL_MELEE, "1d12", "slashing", (P.HEAVY, P.TWO_HANDED)),
    _w("greatsword", "Greatsword", C.MARTIAL_MELEE, "2d6", "slashing", (P.HEAVY, P.TWO_HANDED)),
    _w("halberd", "Halberd", C.MARTIAL_MELEE, "1d10", "slashing", (P.HEAVY, P.REACH, P.TWO_HANDED)),
    _w("lance", "Lance", C.MARTIAL_MELEE, "1d12", "piercing", (P.REACH, P.SPECIAL)),
    _w("longsword", "Longsword", C.MARTIAL_MELEE, "1d8", "slashing", (P.VERSATILE,), versatile="1d10"),
    _w("maul", "Maul", C.MARTIAL_MELEE, "2d6", "bludgeoning", (P.HEAVY, P.TWO_HANDED)),
    _w("morningstar", "Morningstar", C.MARTIAL_MELEE, "1d8", "piercing"),
    _w("pike", "Pike", C.MARTIAL_MELEE, "1d10", "piercing", (P.HEAVY, P.REACH, P.TWO_HANDED)),
    _w("rapier", "Rapier", C.MARTIAL_MELEE, "1d8", "piercing", (P.FINESSE,)),
    _w("scimitar", "Scimitar", C.MARTIAL_MELEE, "1d6", "slashing", (P.FINESSE, P.LIGHT)),
    _w("shortsword", "Shortsword", C.MARTIAL_MELEE, "1d6", "piercing", (P.FINESSE, P.LIGHT)),
    _w("trident", "Trident", C.MARTIAL_MELEE, "1d6", "piercing", (P.THROWN, P.VERSATILE), 20, 60, "1d8"),
    _w("war_pick", "War pick", C.MARTIAL_MELEE, "1d8", "piercing"),
    _w("warhammer", "Warhammer", C.MARTIAL_MELEE, "1d8", "bludgeoning", (P.VERSATILE,), versatile="1d10"),
    _w("whip", "Whip", C.MARTIAL_MELEE, "1d4", "slashing", (P.FINESSE, P.REACH)),
    _w("blowgun", "Blowgun", C.MARTIAL_RANGED, "1", "piercing", (P.AMMUNITION, P.LOADING), 25, 100),
    _w("hand_crossbow", "Hand crossbow", C.MARTIAL_RANGED, "1d6", "piercing", (P.AMMUNITION, P.LIGHT, P.LOADING), 30, 120),
    _w("heavy_crossbow", "Heavy crossbow", C.MARTIAL_RANGED, "1d10", "piercing", (P.AMMUNITION, P.HEAVY, P.LOADING, P.TWO_HANDED), 100, 400),
    _w("longbow", "Longbow", C.MARTIAL_RANGED, "1d8", "piercing", (P.AMMUNITION, P.HEAVY, P.TWO_HANDED), 150, 600),
    _w("net", "Net", C.MARTIAL_RANGED, "0", "none", (P.SPECIAL, P.THROWN), 5, 15),
)

WEAPON_CATALOG = {weapon.key: weapon for weapon in _WEAPONS}


def get_weapon(key: str) -> WeaponDefinition:
    try:
        return WEAPON_CATALOG[key]
    except KeyError as exc:
        raise LookupError(f"unknown SRD weapon: {key}") from exc


def list_weapons() -> tuple[WeaponDefinition, ...]:
    return _WEAPONS
