"""Conservative, evidence-producing coreference resolution over a chat-scoped transcript."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from models.discourse_evidence import (
    DiscourseCandidate,
    DiscourseEvidence,
    DiscourseSource,
    DiscourseSpeaker,
)
from models.entity import Entity
from models.player_intent_analysis import (
    IntentModality,
    IntentPolarity,
    PlayerIntentAnalysis,
)
from models.resolved_conversation_reference import ResolvedConversationReference
from models.semantic_frames import (
    SemanticModality,
    SemanticObjectKind,
    SemanticPolarity,
)
from models.world_state import WorldState
from services.discourse_context import DiscourseContextBuilder

from .entity_reference_resolver import EntityReferenceResolver


@dataclass(frozen=True, slots=True)
class ConversationReferenceResolution:
    references: tuple[ResolvedConversationReference, ...] = ()
    clarification_question: str | None = None
    candidates: tuple[DiscourseCandidate, ...] = ()
    abstention_reason: str | None = None


class ConversationReferenceResolver:
    """Resolve visible references using explicit evidence, type hints and discourse focus.

    The caller must provide history already filtered to the current conversation
    and the active character's visibility. Player input and narrator prose remain
    separate evidence sources; narrator text is never treated as player speech.
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
    _KIND_TYPES: ClassVar[dict[SemanticObjectKind, frozenset[str]]] = {
        SemanticObjectKind.CHARACTER: frozenset({"npc", "character", "person", "humanoid", "player"}),
        SemanticObjectKind.CREATURE: frozenset({"creature", "monster", "beast", "animal"}),
        SemanticObjectKind.LOCATION: frozenset({"location", "place", "room", "building", "area"}),
        SemanticObjectKind.FACTION: frozenset({"faction", "guild", "organization", "group"}),
        SemanticObjectKind.RESOURCE: frozenset({"resource", "currency", "consumable"}),
    }

    MIN_RESOLUTION_SCORE = 35
    MIN_RESOLUTION_MARGIN = 12
    MAX_HISTORY_TURNS = DiscourseContextBuilder.MAX_HISTORY_TURNS

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
    def _turn_parts(turn, world: WorldState | None = None):
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
            if isinstance(turn_id, int) and not isinstance(turn_id, bool) and turn_id > 0
            else None
        )
        parts = []
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
                for attributed in DiscourseContextBuilder.extract_npc_utterances(
                    narrative,
                    valid_id,
                    ConversationReferenceResolver._visible_entities(world),
                ):
                    parts.append((
                        attributed.excerpt,
                        DiscourseSource.NARRATIVE,
                        DiscourseSpeaker.NPC,
                        attributed.speaker_entity_id,
                    ))
        return tuple(parts), valid_id

    @staticmethod
    def _visible_entities(world: WorldState) -> tuple[Entity, ...]:
        visible: list[Entity] = []
        for entity in world.entities.values():
            if not isinstance(entity, Entity) or not entity.active:
                continue
            entity_id = entity.id
            if (
                isinstance(entity_id, bool)
                or not isinstance(entity_id, int)
                or entity_id < 1
                or not entity.name.strip()
                or len(entity.name) > 120
            ):
                continue
            visible.append(entity)
        return tuple(visible)

    def _kind_compatible(self, entity, kind_hint: SemanticObjectKind) -> bool | None:
        expected = self._KIND_TYPES.get(kind_hint)
        if expected is None or kind_hint is SemanticObjectKind.UNKNOWN:
            return None
        entity_type = EntityReferenceResolver.normalize(
            getattr(entity, "entity_type", "")
        )
        type_tokens = set(entity_type.split())
        if not type_tokens:
            return None
        return bool(type_tokens & expected)

    def _mentions_in_part(
        self,
        entity,
        text: str,
        *,
        turn_id: int | None,
        source: DiscourseSource,
        speaker: DiscourseSpeaker,
        recency_rank: int,
        speaker_entity_id: int | None = None,
    ) -> tuple[DiscourseEvidence, ...]:
        normalized = " " + self.entity_resolver.normalize(text) + " "
        mentions = []
        aliases = [getattr(entity, "name", ""), *(getattr(entity, "aliases", []) or [])]
        seen = set()
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip() or len(alias) > 120:
                continue
            normalized_alias = self.entity_resolver.normalize(alias)
            marker = " " + normalized_alias + " "
            if not normalized_alias or marker not in normalized:
                continue
            key = normalized_alias
            if key in seen:
                continue
            seen.add(key)
            mentions.append(
                DiscourseEvidence(
                    turn_id=turn_id,
                    source=source,
                    speaker=speaker,
                    mention=alias[:120],
                    excerpt=text,
                    recency_rank=recency_rank,
                    speaker_entity_id=speaker_entity_id,
                )
            )
        return tuple(mentions)

    def _history_evidence(
        self,
        world: WorldState,
        recent_turns,
        *,
        current_input: str,
    ) -> dict[int, tuple[DiscourseEvidence, ...]]:
        evidence: dict[int, list[DiscourseEvidence]] = {}
        turns = DiscourseContextBuilder.scope_history(
            recent_turns,
            current_input,
        )[-self.MAX_HISTORY_TURNS :]
        visible_entities = self._visible_entities(world)
        for recency_rank, turn in enumerate(reversed(turns), start=1):
            parts, turn_id = self._turn_parts(turn, world)
            for text, source, speaker, speaker_entity_id in parts:
                for entity in visible_entities:
                    entity_id = entity.id
                    if speaker is DiscourseSpeaker.NPC and entity_id != speaker_entity_id:
                        continue
                    mentions = self._mentions_in_part(
                        entity,
                        text,
                        turn_id=turn_id,
                        source=source,
                        speaker=speaker,
                        recency_rank=recency_rank,
                        speaker_entity_id=speaker_entity_id,
                    )
                    if mentions and isinstance(entity_id, int) and not isinstance(entity_id, bool):
                        evidence.setdefault(entity_id, []).extend(mentions)
        return {entity_id: tuple(items) for entity_id, items in evidence.items()}

    def _candidate_score(
        self,
        evidence: tuple[DiscourseEvidence, ...],
        *,
        kind_hint: SemanticObjectKind,
        entity,
    ) -> tuple[int, tuple[str, ...]]:
        score = 0
        signals = []
        best_rank = min(item.recency_rank for item in evidence)
        score += max(10, 70 - (best_rank - 1) * 12)
        signals.append("recency")
        if any(item.source is DiscourseSource.PLAYER_INPUT for item in evidence):
            score += 22
            signals.append("player_authored_focus")
        elif any(item.speaker is DiscourseSpeaker.NPC for item in evidence):
            score += 24
            signals.append("explicit_npc_speaker")
        else:
            score += 8
            signals.append("narrator_context")
        distinct_turns = {item.turn_id for item in evidence if item.turn_id is not None}
        repeat_bonus = min(15, max(0, len(distinct_turns) - 1) * 5)
        if repeat_bonus:
            score += repeat_bonus
            signals.append("topic_continuity")
        kind_match = self._kind_compatible(entity, kind_hint)
        if kind_match is True:
            score += 24
            signals.append("semantic_kind_match")
        elif kind_match is False:
            signals.append("semantic_kind_mismatch")
        return min(1000, score), tuple(signals)

    def _rank_candidates(
        self,
        world: WorldState,
        recent_turns,
        *,
        kind_hint: SemanticObjectKind,
        mention: str,
        current_input: str,
    ) -> tuple[DiscourseCandidate, ...]:
        history = self._history_evidence(
            world,
            recent_turns,
            current_input=current_input,
        )
        pronoun_features = DiscourseContextBuilder.pronoun_agreement(mention)
        candidates = []
        for entity in self._visible_entities(world):
            entity_id = entity.id
            if not isinstance(entity_id, int) or isinstance(entity_id, bool):
                continue
            evidence = history.get(entity_id, ())
            if not evidence:
                continue
            if self._kind_compatible(entity, kind_hint) is False:
                continue
            if pronoun_features is not None:
                gender, number = pronoun_features
                if number == "plural":
                    continue
                observed_features = {
                    DiscourseContextBuilder.grammatical_features(item.excerpt, alias)
                    for item in evidence
                    for alias in (
                        getattr(entity, "name", ""),
                        *(getattr(entity, "aliases", []) or []),
                    )
                    if isinstance(alias, str) and alias.strip()
                }
                observed_features.discard((None, None))
                if observed_features and (gender, number) not in observed_features:
                    continue
            score, signals = self._candidate_score(
                evidence,
                kind_hint=kind_hint,
                entity=entity,
            )
            candidates.append(
                DiscourseCandidate(
                    entity_id=entity_id,
                    entity_name=entity.name,
                    score=score,
                    evidence=evidence,
                    signals=signals,
                )
            )
        return tuple(sorted(candidates, key=lambda item: (-item.score, item.entity_id)))

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
            entity_id = entity.id
            if not isinstance(entity_id, int) or isinstance(entity_id, bool):
                continue
            if entity_id in excluded_ids:
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
                matches.append(entity_id)
        return tuple(matches)

    @staticmethod
    def _candidate_names(candidates: tuple[DiscourseCandidate, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(candidate.entity_name for candidate in candidates))[:4]

    @staticmethod
    def _entity_names(world: WorldState, entity_ids: tuple[int, ...]) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                entity.name
                for entity_id in entity_ids
                if (entity := world.entities.get(entity_id)) is not None
                and isinstance(entity.name, str)
                and entity.name.strip()
            )
        )[:4]

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
        current_input: str | None = None,
    ) -> ConversationReferenceResolution:
        if not isinstance(visible_world, WorldState):
            raise TypeError("visible_world must be a WorldState")
        if not isinstance(analysis, PlayerIntentAnalysis):
            raise TypeError("analysis must be a PlayerIntentAnalysis")
        if not isinstance(recent_turns, (list, tuple)):
            raise TypeError("recent_turns must be a list or tuple")
        if current_input is not None and (
            not isinstance(current_input, str) or not current_input.strip()
        ):
            raise ValueError("current_input must be non-empty text or None")
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
            mentions: list[tuple[str, SemanticObjectKind]] = [
                (mention, SemanticObjectKind.UNKNOWN)
                for mention in step.target_mentions
            ]
            if step.action_frame is not None:
                mentions.extend(
                    (argument.mention.text, argument.mention.kind_hint)
                    for argument in step.action_frame.arguments
                )
            mentions.extend(
                (mention.text, mention.kind_hint)
                for claim in analysis.relation_claims
                if claim.step_index == step.index
                and claim.polarity is SemanticPolarity.POSITIVE
                and claim.modality in {
                    SemanticModality.COMPLETED,
                    SemanticModality.OBSERVED,
                    SemanticModality.REPORTED,
                    SemanticModality.DIALOGUE,
                }
                for mention in (
                    claim.subject,
                    claim.object,
                    *((claim.attributed_to,) if claim.attributed_to is not None else ()),
                )
            )

            # A v1-style flat target and its v2 semantic argument may describe
            # the same surface mention. Merge those records before resolution so
            # an untyped compatibility mention cannot trigger premature ambiguity.
            merged_mentions: dict[str, tuple[str, SemanticObjectKind]] = {}
            conflicting_kinds: set[str] = set()
            conflicting_kind_values: dict[str, set[SemanticObjectKind]] = {}
            for mention, kind_hint in mentions:
                mention_key = self.entity_resolver.normalize(mention)
                if not mention_key:
                    continue
                existing = merged_mentions.get(mention_key)
                if existing is None:
                    merged_mentions[mention_key] = (mention, kind_hint)
                    continue
                existing_kind = existing[1]
                if existing_kind is SemanticObjectKind.UNKNOWN:
                    if mention_key in conflicting_kinds:
                        if kind_hint is not SemanticObjectKind.UNKNOWN:
                            conflicting_kind_values.setdefault(
                                mention_key,
                                set(),
                            ).add(kind_hint)
                    else:
                        merged_mentions[mention_key] = (existing[0], kind_hint)
                elif (
                    kind_hint is not SemanticObjectKind.UNKNOWN
                    and kind_hint is not existing_kind
                ):
                    # Contradictory typed roles must not be resolved by choosing
                    # whichever interpretation happened to appear first.
                    merged_mentions[mention_key] = (
                        existing[0],
                        SemanticObjectKind.UNKNOWN,
                    )
                    conflicting_kinds.add(mention_key)
                    conflicting_kind_values.setdefault(
                        mention_key,
                        {existing_kind, kind_hint},
                    ).update({existing_kind, kind_hint})

            for mention_key, (mention, kind_hint) in merged_mentions.items():
                non_entity_kinds = {
                    SemanticObjectKind.ITEM_DEFINITION,
                    SemanticObjectKind.ITEM_INSTANCE,
                    SemanticObjectKind.RESOURCE,
                    SemanticObjectKind.EVENT,
                }
                if conflicting_kind_values.get(mention_key, set()) & non_entity_kinds:
                    return ConversationReferenceResolution(
                        tuple(references),
                        self._question(mention, ()),
                        abstention_reason="semantic_kind_conflict",
                    )
                # Non-entity namespaces are resolved by WorldReferenceResolver.
                # Never interpret an item/resource/event id as an entity id, and
                # never let an untyped entity candidate steal a typed object pronoun.
                if kind_hint in {
                    SemanticObjectKind.ITEM_DEFINITION,
                    SemanticObjectKind.ITEM_INSTANCE,
                    SemanticObjectKind.RESOURCE,
                    SemanticObjectKind.EVENT,
                }:
                    continue
                match = self.entity_resolver.resolve(visible_world, mention)
                candidate_ids: tuple[int, ...] = ()
                antecedent_turn_id = None
                match_kind = "explicit"
                selected_evidence: tuple[DiscourseEvidence, ...] = ()
                selected_score = 0
                signals: tuple[str, ...] = ()

                if match.status == "resolved":
                    candidate_ids = tuple(candidate.entity_id for candidate in match.candidates)
                    if len(candidate_ids) != 1:
                        return ConversationReferenceResolution(
                            tuple(references),
                            self._question(
                                mention,
                                self._entity_names(visible_world, candidate_ids),
                            ),
                            abstention_reason="explicit_reference_not_unique",
                        )
                    if match.candidates:
                        match_kind = match.candidates[0].match_kind
                elif match.status == "ambiguous" and not self._is_anaphoric(mention):
                    ids = tuple(candidate.entity_id for candidate in match.candidates)
                    names = tuple(
                        visible_world.entities[item].name
                        for item in ids if item in visible_world.entities
                    )
                    return ConversationReferenceResolution(
                        tuple(references),
                        self._question(mention, names),
                        abstention_reason="explicit_reference_ambiguous",
                    )

                if not candidate_ids and self._is_anaphoric(mention):
                    ranked = self._rank_candidates(
                        visible_world,
                        recent_turns,
                        kind_hint=kind_hint,
                        mention=mention,
                        current_input=current_input or step.source_excerpt,
                    )
                    if any(token in self._OTHER_MARKERS for token in self._tokens(mention)):
                        if not ranked:
                            return ConversationReferenceResolution(
                                tuple(references),
                                self._question(mention, ()),
                                abstention_reason="other_role_antecedent_not_established",
                            )
                        antecedent = next(iter(ranked), None)
                        if antecedent is None:
                            return ConversationReferenceResolution(
                                tuple(references),
                                self._question(mention, ()),
                                abstention_reason="other_role_antecedent_not_established",
                            )
                        if antecedent.score < self.MIN_RESOLUTION_SCORE:
                            return ConversationReferenceResolution(
                                tuple(references),
                                self._question(mention, self._candidate_names(ranked)),
                                candidates=ranked[:4],
                                abstention_reason="other_role_antecedent_not_established",
                            )
                        second_antecedent = next(iter(ranked[1:]), None)
                        antecedent_margin = (
                            antecedent.score - second_antecedent.score
                            if second_antecedent is not None
                            else antecedent.score
                        )
                        if (
                            second_antecedent is not None
                            and antecedent_margin < self.MIN_RESOLUTION_MARGIN
                        ):
                            return ConversationReferenceResolution(
                                tuple(references),
                                self._question(mention, self._candidate_names(ranked)),
                                candidates=ranked[:4],
                                abstention_reason="other_role_antecedent_ambiguous",
                            )
                        antecedent_turn_id = next(
                            (
                                item.turn_id
                                for item in antecedent.evidence
                                if item.turn_id is not None
                                and item.recency_rank == min(
                                    evidence.recency_rank
                                    for evidence in antecedent.evidence
                                )
                            ),
                            None,
                        )
                        raw_ids = self._other_role_candidates(
                            visible_world,
                            mention,
                            (antecedent.entity_id,),
                        )
                        role_evidence = DiscourseEvidence(
                            turn_id=None,
                            source=DiscourseSource.PLAYER_INPUT,
                            speaker=DiscourseSpeaker.PLAYER,
                            mention=mention,
                            excerpt=step.source_excerpt,
                            recency_rank=1,
                        )
                        role_candidates = []
                        for entity_id in raw_ids:
                            entity = visible_world.entities.get(entity_id)
                            if (
                                not isinstance(entity, Entity)
                                or self._kind_compatible(entity, kind_hint) is False
                            ):
                                continue
                            role_candidates.append(
                                DiscourseCandidate(
                                    entity_id=entity_id,
                                    entity_name=entity.name,
                                    score=max(35, antecedent.score - 6),
                                    evidence=(role_evidence,),
                                    signals=(
                                        "other_role_in_conversation",
                                        "explicit_role_description",
                                        "contrasted_with_recent_antecedent",
                                    ),
                                )
                            )
                        ranked = tuple(sorted(
                            role_candidates,
                            key=lambda item: (-item.score, item.entity_id),
                        ))
                        match_kind = "other_role_in_conversation"
                    else:
                        match_kind = "conversation_antecedent"

                    selected = next(iter(ranked), None)
                    if selected is None:
                        return ConversationReferenceResolution(
                            tuple(references),
                            self._question(mention, ()),
                            candidates=(),
                            abstention_reason="no_visible_antecedent_evidence",
                        )
                    second_candidate = next(iter(ranked[1:]), None)
                    margin = (
                        selected.score - second_candidate.score
                        if second_candidate is not None
                        else selected.score
                    )
                    if (
                        selected.score < self.MIN_RESOLUTION_SCORE
                        or (
                            second_candidate is not None
                            and margin < self.MIN_RESOLUTION_MARGIN
                        )
                    ):
                        names = self._candidate_names(ranked)
                        return ConversationReferenceResolution(
                            tuple(references),
                            self._question(mention, names),
                            candidates=ranked[:4],
                            abstention_reason="discourse_candidates_ambiguous",
                        )
                    candidate_ids = (selected.entity_id,)
                    selected_evidence = selected.evidence
                    selected_score = selected.score
                    signals = selected.signals
                    selected_turn_id = next(
                        (
                            item.turn_id for item in selected.evidence
                            if item.turn_id is not None
                            and item.recency_rank == min(
                                evidence.recency_rank for evidence in selected.evidence
                            )
                        ),
                        None,
                    )
                    if selected_turn_id is not None:
                        antecedent_turn_id = selected_turn_id

                elif not candidate_ids:
                    # A genuinely new proper name may be an intentional new entity.
                    continue

                entity_id = candidate_ids[0]
                entity = visible_world.entities.get(entity_id)
                if entity is None or not getattr(entity, "active", False):
                    return ConversationReferenceResolution(
                        tuple(references),
                        self._question(mention, ()),
                        abstention_reason="resolved_entity_not_visible",
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
                            evidence=selected_evidence,
                            confidence_score=selected_score,
                            resolution_signals=signals,
                        )
                    )
                    seen.add(key)

        return ConversationReferenceResolution(tuple(references))
