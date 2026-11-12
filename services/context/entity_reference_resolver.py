"""Conservative, deterministic matching of player references to known entities."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from models.entity import Entity
from models.world_state import WorldState

ReferenceStatus = Literal["resolved", "ambiguous", "unresolved"]


@dataclass(frozen=True, slots=True)
class EntityReferenceCandidate:
    """One entity that has evidence matching a natural-language reference."""

    entity_id: int
    score: int
    match_kind: str
    matched_reference: str


@dataclass(frozen=True, slots=True)
class EntityReferenceResolution:
    """A deterministic result that can explicitly abstain instead of guessing."""

    status: ReferenceStatus
    candidates: tuple[EntityReferenceCandidate, ...] = ()

    @property
    def entity_ids(self) -> tuple[int, ...]:
        if self.status != "resolved":
            return ()
        return tuple(candidate.entity_id for candidate in self.candidates)

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)


class EntityReferenceResolver:
    """Resolve proper names, explicit aliases and unambiguous role descriptions.

    This is lexical evidence, not open-ended semantic inference. Free-form notes
    are a low-priority compatibility fallback; explicit names and aliases win.
    """

    _TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
    _STOPWORDS = frozenset(
    {
        "a",
        "al",
        "algo",
        "algun",
        "alguna",
        "algunos",
        "algunas",
        "ante",
        "aqui",
        "aquel",
        "aquella",
        "aquello",
        "aquellos",
        "aquellas",
        "asi",
        "bajo",
        "cada",
        "como",
        "con",
        "contra",
        "cual",
        "cuales",
        "cuando",
        "de",
        "del",
        "desde",
        "donde",

        "el",
        "ella",
        "ellas",
        "ello",
        "ellos",
        "en",
        "entre",
        "era",
        "es",
        "esa",
        "esas",
        "ese",
        "eso",
        "esos",
        "esta",
        "estaba",
        "estaban",
        "estado",
        "estas",
        "este",
        "esto",
        "estos",
        "fue",
        "fueron",
        "ha",
        "han",
        "hasta",
        "hay",
        "la",
        "las",
        "le",
        "les",
        "lo",
        "los",
        "mas",
        "me",
        "mi",
        "mia",
        "mismo",
        "muy",
        "nada",
        "ni",
        "no",
        "nos",
        "o",
        "os",
        "otra",
        "otras",
        "otro",
        "otros",
        "para",
        "pero",
        "por",
        "porque",
        "que",
        "quien",
        "quienes",
        "se",
        "segun",
        "sin",
        "sobre",
        "soy",
        "su",
        "sus",
        "te",
        "tenemos",
        "tiene",
        "tienen",
        "tu",
        "tus",
        "un",
        "una",

        "unos",
        "unas",
        "y",
        "ya",
        "yo",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "for",
        "from",
        "he",
        "her",
        "him",
        "his",
        "how",
        "i",
        "in",
        "is",
        "it",
        "my",
        "of",
        "on",
        "or",
        "our",
        "she",
        "that",
        "their",
        "them",
        "they",
        "this",
        "to",
        "us",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "with",
        "you",
        "your",
        "quiero",
        "quisiera",
        "podria",
        "podrias",
        "puede",
        "pueden",
        "puedo",
        "deseas",
        "deseo",
        "hablar",
        "habla",
        "hablo",
        "hablarle",
        "hablarles",
        "hablame",
        "pregunto",
        "preguntar",
        "pregunta",
        "preguntas",
        "saludar",
        "saludo",
        "saluda",
        "conocer",
        "conozco",
        "conoces",
        "conoce",
        "busco",
        "buscar",
        "busca",
        "buscarle",
        "encuentra",
        "encontrar",
        "dime",
        "decime",
        "cuenta",
        "cuentame",
        "decir",
        "decirme",
        "mostrar",
        "muestra",
        "ensename",
        "entrar",
        "entra",
        "voy",
        "ir",
        "mira",
        "mirar",
        "observar",
        "observa",
        "atacar",
        "ataca",
        "luchar",
        "necesito",
        "talk",
        "speak",
        "speaking",
        "ask",
        "asking",
        "tell",
        "telling",
        "meet",
        "meeting",
        "greet",
        "find",
        "looking",
        "show",
        "want",
        "would",
        "please",
        "could",
        "should",
    }
)

    def resolve(
        self,
        world: WorldState,
        query: str,
    ) -> EntityReferenceResolution:
        if not isinstance(world, WorldState):
            raise TypeError("world must be a WorldState")
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        normalized_query = self.normalize(query)
        query_tokens = self._significant_tokens(normalized_query)
        if not normalized_query or not query_tokens:
            return EntityReferenceResolution("unresolved")

        explicit: dict[int, EntityReferenceCandidate] = {}
        explicit_owners: dict[str, set[int]] = {}
        descriptive: dict[int, EntityReferenceCandidate] = {}
        for entity in world.entities.values():
            if not isinstance(entity, Entity) or not entity.active:
                continue
            if isinstance(entity.id, bool) or not isinstance(entity.id, int):
                continue
            references = [(entity.name, "name", 130, 120)]
            references.extend((alias, "alias", 125, 115) for alias in entity.aliases)
            for value, kind, exact_score, token_score in references:
                match = self._match_reference(normalized_query, query_tokens, value)
                if match is None:
                    continue
                exact_phrase, reference = match
                candidate = EntityReferenceCandidate(
                    entity_id=entity.id,
                    score=exact_score if exact_phrase else token_score,
                    match_kind=kind,
                    matched_reference=reference,
                )
                current = explicit.get(entity.id)
                if current is None or candidate.score > current.score:
                    explicit[entity.id] = candidate
                explicit_owners.setdefault(reference, set()).add(entity.id)

            if self._match_description(query_tokens, entity.description):
                descriptive[entity.id] = EntityReferenceCandidate(
                    entity_id=entity.id,
                    score=80 + min(len(query_tokens), 10),
                    match_kind="description",
                    matched_reference=" ".join(sorted(query_tokens)),
                )
            if self._match_description(query_tokens, entity.notes):
                note_candidate = EntityReferenceCandidate(
                    entity_id=entity.id,
                    score=60 + min(len(query_tokens), 10),
                    match_kind="notes",
                    matched_reference=" ".join(sorted(query_tokens)),
                )
                current = descriptive.get(entity.id)
                if current is None or note_candidate.score > current.score:
                    descriptive[entity.id] = note_candidate

        collisions = [
            owners for owners in explicit_owners.values() if len(owners) > 1
        ]
        if collisions:
            ambiguous_ids = set().union(*collisions)
            candidates = tuple(sorted(
                (explicit[key] for key in ambiguous_ids if key in explicit),
                key=lambda item: (-item.score, item.entity_id),
            ))
            return EntityReferenceResolution("ambiguous", candidates)
        if explicit:
            candidates = tuple(sorted(
                explicit.values(), key=lambda item: (-item.score, item.entity_id)
            ))
            return EntityReferenceResolution("resolved", candidates)
        if not descriptive:
            return EntityReferenceResolution("unresolved")

        ordered = sorted(
            descriptive.values(), key=lambda item: (-item.score, item.entity_id)
        )
        strongest = ordered[0]
        contenders = tuple(
            candidate for candidate in ordered
            if strongest.score - candidate.score < 15
        )
        if len(contenders) > 1:
            return EntityReferenceResolution("ambiguous", contenders)
        return EntityReferenceResolution("resolved", (strongest,))

    @classmethod
    def normalize(cls, value: str) -> str:
        """Case-fold, remove diacritics and normalize punctuation/spacing."""
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        plain = "".join(
            character for character in decomposed
            if not unicodedata.combining(character)
        )
        return " ".join(cls._TOKEN_PATTERN.findall(plain))

    @classmethod
    def _significant_tokens(cls, value: str) -> frozenset[str]:
        return frozenset(
            token for token in cls._TOKEN_PATTERN.findall(value)
            if len(token) >= 2 and token not in cls._STOPWORDS
        )

    @classmethod
    def _match_reference(
        cls,
        normalized_query: str,
        query_tokens: frozenset[str],
        value: str,
    ) -> tuple[bool, str] | None:
        normalized_value = cls.normalize(value)
        value_tokens = cls._significant_tokens(normalized_value)
        if not value_tokens or not value_tokens.issubset(query_tokens):
            return None
        exact = f" {normalized_value} " in f" {normalized_query} "
        return exact, " ".join(sorted(value_tokens))

    @classmethod
    def _match_description(
        cls,
        query_tokens: frozenset[str],
        value: str,
    ) -> bool:
        if not value:
            return False
        value_tokens = cls._significant_tokens(cls.normalize(value))
        return bool(query_tokens) and query_tokens.issubset(value_tokens)
