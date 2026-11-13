"""Conservative coreference resolution over a chat-scoped, visible transcript."""

from __future__ import annotations

from dataclasses import dataclass

from models.player_intent_analysis import (
    IntentModality,
    IntentPolarity,
    PlayerIntentAnalysis,
)
from models.resolved_conversation_reference import ResolvedConversationReference
from models.world_state import WorldState

from .entity_reference_resolver import EntityReferenceResolver


@dataclass(frozen=True, slots=True)
class ConversationReferenceResolution:
    references: tuple[ResolvedConversationReference, ...] = ()
    clarification_question: str | None = None


class ConversationReferenceResolver:
    """Resolve explicit references and unique recent-turn antecedents.

    The caller supplies the active-character-filtered proposal projection and
    history already isolated to the current conversation. No model-selected
    entity identifiers are accepted; ambiguous references are clarified.
    """

    _PRONOUNS = frozenset({
        "el", "ella", "ello", "ellos", "ellas", "le", "les", "lo", "la",
        "los", "las", "him", "her", "he", "she", "it", "they", "them",
    })
    _DEMONSTRATIVES = frozenset({
        "ese", "esa", "eso", "esos", "esas", "este", "esta", "esto",
        "estos", "estas", "aquel", "aquella", "aquello", "aquellos",
        "aquellas", "this", "that", "these", "those",
    })
    _SAME_REFERENTS = frozenset({"mismo", "misma", "mismos", "mismas", "same", "again"})
    _OTHER_MARKERS = frozenset({"otro", "otra", "otros", "otras", "other", "another"})
    _ROLE_TERMS = frozenset({
        "guardia", "guard", "soldado", "soldier", "capitan", "captain",
        "tabernero", "innkeeper", "mago", "wizard", "clerigo", "cleric",
        "arquero", "archer", "mercader", "merchant", "ladron", "thief",
    })
    _ELIGIBLE_MODALITIES = frozenset({
        IntentModality.ATTEMPTED,
        IntentModality.COMPLETED,
        IntentModality.OBSERVED,
        IntentModality.REPORTED,
        IntentModality.CORRECTION,
        IntentModality.DIALOGUE,
    })

    def __init__(self, entity_resolver: EntityReferenceResolver | None = None) -> None:
        if entity_resolver is not None and not isinstance(entity_resolver, EntityReferenceResolver):
            raise TypeError("entity_resolver must be an EntityReferenceResolver or None")
        self.entity_resolver = entity_resolver or EntityReferenceResolver()

    @classmethod
    def _tokens(cls, value: str) -> tuple[str, ...]:
        return tuple(EntityReferenceResolver.normalize(value).split())

    @classmethod
    def _is_anaphoric(cls, mention: str) -> bool:
        tokens = cls._tokens(mention)
        if not tokens:
            return False
        return (
            (len(tokens) == 1 and tokens[0] in cls._PRONOUNS)
            or tokens[0] in cls._DEMONSTRATIVES
            or any(token in cls._SAME_REFERENTS for token in tokens)
            or any(token in cls._OTHER_MARKERS for token in tokens)
        )

    @staticmethod
    def _turn_text(turn) -> tuple[str, int | None]:
        if isinstance(turn, dict):
            player_input = turn.get("player_input", "")
            narrative = turn.get("narrative", "")
            turn_id = turn.get("id")
        else:
            player_input = getattr(turn, "player_input", "")
            narrative = getattr(turn, "narrative", "")
            turn_id = getattr(turn, "id", None)
        parts = [
            value[:1200]
            for value in (player_input, narrative)
            if isinstance(value, str) and value.strip()
        ]
        valid_id = (
            turn_id
            if isinstance(turn_id, int) and not isinstance(turn_id, bool) and turn_id > 0
            else None
        )
        return " ".join(parts), valid_id

    @staticmethod
    def _visible_entities(world: WorldState):
        visible = []
        for entity in world.entities.values():
            entity_id = getattr(entity, "id", None)
            if (
                not getattr(entity, "active", False)
                or not isinstance(entity_id, int)
                or isinstance(entity_id, bool)
                or entity_id <= 0
            ):
                continue
            visible.append(entity)
        return visible

    def _entities_mentioned_in_turn(self, world: WorldState, turn_text: str) -> tuple[int, ...]:
        normalized = " " + self.entity_resolver.normalize(turn_text) + " "
        found: list[tuple[int, int]] = []
        for entity in self._visible_entities(world):
            positions = []
            for alias in [entity.name, *(getattr(entity, "aliases", []) or [])]:
                if not isinstance(alias, str) or not alias.strip():
                    continue
                normalized_alias = self.entity_resolver.normalize(alias)
                marker = " " + normalized_alias + " "
                position = normalized.rfind(marker) if normalized_alias else -1
                if position >= 0:
                    positions.append(position)
            entity_id = getattr(entity, "id", None)
            if positions and isinstance(entity_id, int) and not isinstance(entity_id, bool):
                found.append((max(positions), entity_id))
        found.sort(reverse=True)
        return tuple(entity_id for _position, entity_id in found)

    def _nearest_antecedent(
        self,
        world: WorldState,
        recent_turns,
    ) -> tuple[tuple[int, ...], int | None]:
        for turn in reversed(recent_turns[-6:]):
            text, turn_id = self._turn_text(turn)
            if not text:
                continue
            ids = self._entities_mentioned_in_turn(world, text)
            if ids:
                return ids, turn_id
        return (), None

    def _other_role_candidates(
        self,
        world: WorldState,
        mention: str,
        excluded_ids: tuple[int, ...],
    ) -> tuple[int, ...]:
        role_terms = set(self._tokens(mention)) & self._ROLE_TERMS
        if not role_terms:
            return ()
        matches = []
        for entity in self._visible_entities(world):
            if entity.id in excluded_ids:
                continue
            evidence = " ".join(
                value
                for value in (
                    getattr(entity, "name", ""),
                    getattr(entity, "entity_type", ""),
                    getattr(entity, "description", ""),
                    getattr(entity, "notes", ""),
                )
                if isinstance(value, str)
            )
            if role_terms & set(self._tokens(evidence)):
                matches.append(entity.id)
        return tuple(matches)

    @staticmethod
    def _candidate_names(world: WorldState, ids: tuple[int, ...]) -> tuple[str, ...]:
        names = []
        for entity_id in ids:
            entity = world.entities.get(entity_id)
            if entity is not None and isinstance(entity.name, str) and entity.name.strip():
                names.append(entity.name.strip())
        return tuple(dict.fromkeys(names))[:4]

    @classmethod
    def _question(cls, mention: str, candidates: tuple[str, ...]) -> str:
        safe = mention.strip()[:90]
        if candidates:
            return f"¿A cuál te refieres con «{safe}»: {', '.join(candidates)}?"[:300]
        return f"¿A quién o a qué te refieres con «{safe}»?"[:300]

    def resolve(
        self,
        visible_world: WorldState,
        analysis: PlayerIntentAnalysis,
        *,
        recent_turns=(),
    ) -> ConversationReferenceResolution:
        if not isinstance(visible_world, WorldState):
            raise TypeError("visible_world must be a WorldState")
        if not isinstance(analysis, PlayerIntentAnalysis):
            raise TypeError("analysis must be a PlayerIntentAnalysis")
        if not isinstance(recent_turns, (list, tuple)):
            raise TypeError("recent_turns must be a list or tuple")
        if not analysis.allows_world_proposal:
            return ConversationReferenceResolution()

        last_step = (
            analysis.active_step_index
            if analysis.active_step_index is not None
            else len(analysis.steps) - 1
        )
        references: list[ResolvedConversationReference] = []
        seen: set[tuple[str, int]] = set()

        for step in analysis.steps[: last_step + 1]:
            if (
                step.polarity is not IntentPolarity.POSITIVE
                or step.modality not in self._ELIGIBLE_MODALITIES
            ):
                continue
            for mention in step.target_mentions:
                match = self.entity_resolver.resolve(visible_world, mention)
                candidate_ids: tuple[int, ...] = ()
                antecedent_turn_id = None
                match_kind = "explicit"

                if match.status == "resolved":
                    candidate_ids = tuple(candidate.entity_id for candidate in match.candidates)
                    if len(candidate_ids) != 1:
                        return ConversationReferenceResolution(
                            tuple(references),
                            self._question(mention, self._candidate_names(visible_world, candidate_ids)),
                        )
                    if match.candidates:
                        match_kind = match.candidates[0].match_kind
                elif match.status == "ambiguous" and not self._is_anaphoric(mention):
                    ids = tuple(candidate.entity_id for candidate in match.candidates)
                    return ConversationReferenceResolution(
                        tuple(references),
                        self._question(mention, self._candidate_names(visible_world, ids)),
                    )

                if not candidate_ids and self._is_anaphoric(mention):
                    antecedents, antecedent_turn_id = self._nearest_antecedent(
                        visible_world,
                        recent_turns,
                    )
                    if any(token in self._OTHER_MARKERS for token in self._tokens(mention)):
                        candidate_ids = self._other_role_candidates(
                            visible_world,
                            mention,
                            antecedents,
                        )
                        match_kind = "other_role_in_conversation"
                    else:
                        candidate_ids = antecedents if len(antecedents) == 1 else ()
                        match_kind = "conversation_antecedent"
                    if len(candidate_ids) != 1:
                        return ConversationReferenceResolution(
                            tuple(references),
                            self._question(
                                mention,
                                self._candidate_names(visible_world, candidate_ids or antecedents),
                            ),
                        )
                elif not candidate_ids:
                    # A genuinely new proper name may be an intentional new NPC/item.
                    continue

                entity_id = candidate_ids[0]
                entity = visible_world.entities.get(entity_id)
                if entity is None or not getattr(entity, "active", False):
                    return ConversationReferenceResolution(
                        tuple(references),
                        self._question(mention, ()),
                    )
                key = (self.entity_resolver.normalize(mention), entity_id)
                if key not in seen:
                    references.append(
                        ResolvedConversationReference(
                            mention=mention,
                            entity_id=entity_id,
                            entity_name=entity.name,
                            match_kind=match_kind,
                            antecedent_turn_id=antecedent_turn_id,
                        )
                    )
                    seen.add(key)

        return ConversationReferenceResolution(tuple(references))
