"""Build typed, provenance-preserving antecedent evidence bundles."""

from __future__ import annotations

import re
import unicodedata

from models.discourse_evidence import (
    ConversationReferenceMention,
    DiscourseEvidence,
    DiscourseEvidenceBundle,
    DiscourseSource,
    DiscourseSpeaker,
    EntityDiscourseEvidence,
)
from models.entity import Entity
from models.world_state import WorldState
from services.context.entity_reference_resolver import EntityReferenceResolver
from services.discourse_context import DiscourseContextBuilder


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _normalized_token_spans(value: str) -> tuple[tuple[str, int, int], ...]:
    """Return normalized tokens with offsets mapped back to original text."""
    normalized_chars: list[str] = []
    source_positions: list[int] = []
    for position, character in enumerate(value):
        for normalized_character in unicodedata.normalize("NFKD", character.casefold()):
            if unicodedata.combining(normalized_character):
                continue
            normalized_chars.append(normalized_character)
            source_positions.append(position)

    normalized = "".join(normalized_chars)
    return tuple(
        (
            match.group(),
            source_positions[match.start()],
            source_positions[match.end() - 1] + 1,
        )
        for match in _TOKEN_PATTERN.finditer(normalized)
    )


def _literal_alias_offsets(text: str, alias: str) -> tuple[int | None, int | None]:
    """Find a whole-token alias occurrence without matching inside longer words."""
    alias_tokens = tuple(EntityReferenceResolver.normalize(alias).split())
    if not alias_tokens:
        return None, None
    text_tokens = _normalized_token_spans(text)
    width = len(alias_tokens)
    for start_index in range(len(text_tokens) - width + 1):
        observed = tuple(
            token for token, _start, _end
            in text_tokens[start_index:start_index + width]
        )
        if observed != alias_tokens:
            continue
        start_offset = text_tokens[start_index][1]
        end_offset = text_tokens[start_index + width - 1][2]
        # DiscourseEvidence offsets promise the exact literal spelling. When
        # only accent-insensitive normalization matched, retain evidence but
        # deliberately omit offsets rather than publishing an inaccurate span.
        if text[start_offset:end_offset].casefold() == alias.casefold():
            return start_offset, end_offset
    return None, None


class ConversationReferenceEvidenceExtractor:
    """Extract bounded chat-local evidence after the caller applies visibility.

    This component never assigns a referent to a player mention. It only records
    literal antecedent occurrences attached to entities already present in the
    supplied visible-world projection.
    """

    MAX_HISTORY_TURNS = DiscourseContextBuilder.MAX_HISTORY_TURNS

    def __init__(self, entity_resolver: EntityReferenceResolver | None = None) -> None:
        if entity_resolver is not None and not isinstance(
            entity_resolver, EntityReferenceResolver
        ):
            raise TypeError(
                "entity_resolver must be an EntityReferenceResolver or None"
            )
        self.entity_resolver = entity_resolver or EntityReferenceResolver()

    @staticmethod
    def visible_entities(world: WorldState) -> tuple[Entity, ...]:
        """Return only active, well-formed entities from the caller's projection."""
        visible: list[Entity] = []
        for entity in world.entities.values():
            if not isinstance(entity, Entity) or not entity.active:
                continue
            entity_id = entity.id
            if (
                isinstance(entity_id, bool)
                or not isinstance(entity_id, int)
                or entity_id < 1
                or not isinstance(entity.name, str)
                or not entity.name.strip()
                or len(entity.name) > 120
            ):
                continue
            visible.append(entity)
        return tuple(visible)

    @classmethod
    def turn_parts(
        cls,
        turn: object,
        world: WorldState | None = None,
    ) -> tuple[tuple[tuple[str, DiscourseSource, DiscourseSpeaker, int | None], ...], int | None]:
        """Separate player-authored text, narrator prose and explicit NPC quotes."""
        if isinstance(turn, dict):
            player_input = turn.get("player_input", "")
            narrative = turn.get("narrative", "")
            turn_id = turn.get("id")
        else:
            player_input = getattr(turn, "player_input", "")
            narrative = getattr(turn, "narrative", "")
            turn_id = getattr(turn, "id", None)
        valid_id = (
            turn_id
            if isinstance(turn_id, int)
            and not isinstance(turn_id, bool)
            and turn_id > 0
            else None
        )
        parts: list[tuple[str, DiscourseSource, DiscourseSpeaker, int | None]] = []
        if isinstance(player_input, str) and player_input.strip():
            parts.append((
                player_input[:1200],
                DiscourseSource.PLAYER_INPUT,
                DiscourseSpeaker.PLAYER,
                None,
            ))
        if isinstance(narrative, str) and narrative.strip():
            parts.append((
                narrative[:1200],
                DiscourseSource.NARRATIVE,
                DiscourseSpeaker.NARRATOR,
                None,
            ))
            if world is not None:
                visible_entities = cls.visible_entities(world)
                for attributed in DiscourseContextBuilder.extract_npc_utterances(
                    narrative,
                    valid_id,
                    visible_entities,
                ):
                    parts.append((
                        attributed.excerpt[:1200],
                        DiscourseSource.NARRATIVE,
                        DiscourseSpeaker.NPC,
                        attributed.speaker_entity_id,
                    ))
        return tuple(parts), valid_id

    def mentions_in_part(
        self,
        entity: Entity,
        text: str,
        *,
        turn_id: int | None,
        source: DiscourseSource,
        speaker: DiscourseSpeaker,
        recency_rank: int,
        speaker_entity_id: int | None = None,
    ) -> tuple[DiscourseEvidence, ...]:
        """Record literal aliases with source/speaker/turn provenance and offsets."""
        normalized = " " + self.entity_resolver.normalize(text) + " "
        mentions: list[DiscourseEvidence] = []
        aliases = [entity.name, *(getattr(entity, "aliases", []) or [])]
        seen: set[str] = set()
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip() or len(alias) > 120:
                continue
            normalized_alias = self.entity_resolver.normalize(alias)
            marker = " " + normalized_alias + " "
            if not normalized_alias or marker not in normalized:
                continue
            if normalized_alias in seen:
                continue
            seen.add(normalized_alias)
            start_offset, end_offset = _literal_alias_offsets(text, alias)
            mentions.append(
                DiscourseEvidence(
                    turn_id=turn_id,
                    source=source,
                    speaker=speaker,
                    mention=alias[:120],
                    excerpt=text,
                    recency_rank=recency_rank,
                    speaker_entity_id=speaker_entity_id,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
            )
        return tuple(mentions)

    def extract(
        self,
        world: WorldState,
        recent_turns: list[object] | tuple[object, ...],
        *,
        current_input: str,
        mentions: tuple[ConversationReferenceMention, ...] = (),
    ) -> DiscourseEvidenceBundle:
        """Build one immutable evidence snapshot for a single step/selection scope."""
        selection = DiscourseContextBuilder.select_history(
            recent_turns,
            current_input,
        )
        turns = selection.turns[-self.MAX_HISTORY_TURNS :]
        visible_entities = self.visible_entities(world)
        evidence_by_entity: dict[int, list[DiscourseEvidence]] = {}

        for recency_rank, turn in enumerate(reversed(turns), start=1):
            parts, turn_id = self.turn_parts(turn, world)
            for text, source, speaker, speaker_entity_id in parts:
                for entity in visible_entities:
                    entity_id = entity.id
                    if (
                        isinstance(entity_id, bool)
                        or not isinstance(entity_id, int)
                        or entity_id < 1
                    ):
                        continue
                    if speaker is DiscourseSpeaker.NPC and entity_id != speaker_entity_id:
                        continue
                    found = self.mentions_in_part(
                        entity,
                        text,
                        turn_id=turn_id,
                        source=source,
                        speaker=speaker,
                        recency_rank=recency_rank,
                        speaker_entity_id=speaker_entity_id,
                    )
                    if found:
                        evidence_by_entity.setdefault(entity_id, []).extend(found)

        entity_evidence = tuple(
            EntityDiscourseEvidence(
                entity_id=entity_id,
                evidence=tuple(evidence),
            )
            for entity_id, evidence in sorted(evidence_by_entity.items())
        )
        selected_turn_ids = tuple(dict.fromkeys(
            turn_id
            for _turn in turns
            for _parts, turn_id in (self.turn_parts(_turn),)
            if turn_id is not None
        ))
        return DiscourseEvidenceBundle(
            mentions=mentions,
            entity_evidence=entity_evidence,
            selection_reason=selection.reason,
            selected_turn_count=len(turns),
            selected_turn_ids=selected_turn_ids,
            anchor_tokens=tuple(selection.anchor_tokens[:24]),
            selection_ambiguous=selection.ambiguous,
        )
