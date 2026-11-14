"""Resolve typed, non-entity world references conservatively across turns."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from models.discourse_evidence import (
    DiscourseEvidence,
    DiscourseSource,
    DiscourseSpeaker,
)
from models.event import Event
from models.item import Item, ItemInstance
from models.player_intent_analysis import (
    IntentModality,
    IntentPolarity,
    PlayerIntentAnalysis,
)
from models.resolved_world_reference import (
    ResolvedWorldReference,
    WorldReferenceCategory,
)
from models.resource import Resource
from models.semantic_frames import (
    SemanticModality,
    SemanticObjectKind,
    SemanticPolarity,
)
from models.world_state import WorldState
from services.discourse_context import DiscourseContextBuilder

from .entity_reference_resolver import EntityReferenceResolver


@dataclass(frozen=True, slots=True)
class _WorldReferent:
    category: WorldReferenceCategory
    referent_id: int | str
    name: str
    aliases: tuple[str, ...]
    searchable_text: str


@dataclass(frozen=True, slots=True)
class WorldReferenceResolution:
    references: tuple[ResolvedWorldReference, ...] = ()
    clarification_question: str | None = None
    abstention_reason: str | None = None
    candidates: tuple[str, ...] = ()


class WorldReferenceResolver:
    """Resolve item definitions, physical item copies, resources and visible events.

    Entity records remain the responsibility of EntityReferenceResolver. Keeping
    these namespaces separate prevents an item id from being mistaken for an
    entity id and prevents a definition from being confused with one physical copy.
    """

    _KIND_CATEGORY: ClassVar[dict[SemanticObjectKind, WorldReferenceCategory]] = {
        SemanticObjectKind.ITEM_DEFINITION: WorldReferenceCategory.ITEM_DEFINITION,
        SemanticObjectKind.ITEM_INSTANCE: WorldReferenceCategory.ITEM_INSTANCE,
        SemanticObjectKind.RESOURCE: WorldReferenceCategory.RESOURCE,
        SemanticObjectKind.EVENT: WorldReferenceCategory.EVENT,
    }
    _PRONOUNS = frozenset({
        "el", "ella", "ello", "ellos", "ellas", "lo", "la", "los", "las",
        "eso", "esto", "ese", "esa", "esos", "esas", "este", "esta",
        "aquello", "aquel", "aquella", "him", "her", "it", "they", "them",
        "this", "that", "these", "those",
    })
    _SAME_MARKERS = frozenset({"mismo", "misma", "mismos", "mismas", "same", "again"})
    _STOPWORDS = frozenset({
        "a", "al", "de", "del", "el", "la", "las", "lo", "los", "un", "una",
        "unos", "unas", "mi", "mis", "su", "sus", "ese", "esa", "eso",
        "estos", "estas", "este", "esta", "the", "an", "of", "to",
        "my", "his", "her", "their", "this", "that", "same",
        "mismo", "misma", "mismos", "mismas",
    })
    _ELIGIBLE_STEP_MODALITIES = frozenset({
        IntentModality.ATTEMPTED,
        IntentModality.COMPLETED,
        IntentModality.OBSERVED,
        IntentModality.REPORTED,
        IntentModality.CORRECTION,
        IntentModality.DIALOGUE,
    })

    MIN_RESOLUTION_SCORE = 35
    MIN_RESOLUTION_MARGIN = 12
    MAX_REFERENCES = 16
    MAX_HISTORY_TURNS = DiscourseContextBuilder.MAX_HISTORY_TURNS

    @staticmethod
    def _normalize(value: str) -> str:
        return EntityReferenceResolver.normalize(value)

    @classmethod
    def _tokens(cls, value: str) -> frozenset[str]:
        return frozenset(
            token for token in cls._normalize(value).split()
            if token and token not in cls._STOPWORDS
        )

    @classmethod
    def _is_anaphoric(cls, mention: str) -> bool:
        tokens = cls._normalize(mention).split()
        return bool(
            (len(tokens) == 1 and tokens[0] in cls._PRONOUNS)
            or (tokens and tokens[0] in {"ese", "esa", "eso", "este", "esta", "aquel", "aquella", "this", "that"})
            or any(token in cls._SAME_MARKERS for token in tokens)
        )

    @classmethod
    def _has_lexical_head(cls, mention: str) -> bool:
        tokens = cls._tokens(mention)
        return bool(tokens - cls._PRONOUNS - cls._SAME_MARKERS)

    @staticmethod
    def _turn_parts(turn):
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
            parts.append((player_input[:1200], DiscourseSource.PLAYER_INPUT, DiscourseSpeaker.PLAYER))
        if isinstance(narrative, str) and narrative.strip():
            parts.append((narrative[:1200], DiscourseSource.NARRATIVE, DiscourseSpeaker.NARRATOR))
        return tuple(parts), valid_id

    @classmethod
    def _collect(
        cls,
        world: WorldState,
        *,
        character_entity_id: int | None,
    ) -> dict[WorldReferenceCategory, tuple[_WorldReferent, ...]]:
        grouped: dict[WorldReferenceCategory, list[_WorldReferent]] = {
            category: [] for category in WorldReferenceCategory
        }
        for item in world.items.values():
            if not isinstance(item, Item) or not isinstance(item.id, int) or isinstance(item.id, bool) or item.id < 1:
                continue
            if not item.name.strip():
                continue
            grouped[WorldReferenceCategory.ITEM_DEFINITION].append(
                _WorldReferent(
                    WorldReferenceCategory.ITEM_DEFINITION,
                    item.id,
                    item.name[:160],
                    (item.name,),
                    f"{item.name} {item.description} {item.significance} {item.notes}",
                )
            )
        for instance in world.item_instances.values():
            if (
                not isinstance(instance, ItemInstance)
                or not instance.active
                or not isinstance(instance.id, int)
                or isinstance(instance.id, bool)
                or instance.id < 1
            ):
                continue
            item = world.items.get(instance.item_id)
            if not isinstance(item, Item) or not item.name.strip():
                continue
            aliases = [item.name, f"{item.name} #{instance.instance_number}"]
            if instance.notes.strip():
                aliases.append(instance.notes[:120])
            grouped[WorldReferenceCategory.ITEM_INSTANCE].append(
                _WorldReferent(
                    WorldReferenceCategory.ITEM_INSTANCE,
                    instance.id,
                    f"{item.name} (instancia #{instance.instance_number})"[:160],
                    tuple(aliases),
                    f"{item.name} {instance.condition} {instance.notes}",
                )
            )
        for resource in world.resources.values():
            if not isinstance(resource, Resource) or not isinstance(resource.id, int) or isinstance(resource.id, bool) or resource.id < 1:
                continue
            if not resource.name.strip():
                continue
            grouped[WorldReferenceCategory.RESOURCE].append(
                _WorldReferent(
                    WorldReferenceCategory.RESOURCE,
                    resource.id,
                    resource.name[:160],
                    (resource.name,),
                    f"{resource.name} {resource.resource_type} {resource.unit} {resource.notes}",
                )
            )
        for event in world.events.values():
            if not isinstance(event, Event) or not event.title.strip():
                continue
            if event.secret or event.visibility_scope == "gm_only":
                continue
            if event.visibility_scope == "character" and (
                character_entity_id is None
                or character_entity_id not in event.known_by_entity_ids
            ):
                continue
            grouped[WorldReferenceCategory.EVENT].append(
                _WorldReferent(
                    WorldReferenceCategory.EVENT,
                    event.id,
                    event.title[:160],
                    (event.title,),
                    f"{event.title} {event.description}",
                )
            )
        return {
            category: tuple(sorted(items, key=lambda item: (item.name.casefold(), str(item.referent_id))))
            for category, items in grouped.items()
        }

    @classmethod
    def _explicit_matches(
        cls,
        mention: str,
        candidates: tuple[_WorldReferent, ...],
    ) -> tuple[tuple[_WorldReferent, str, int], ...]:
        query = cls._tokens(mention)
        if not query:
            return ()
        matches = []
        for candidate in candidates:
            name_tokens = cls._tokens(candidate.name)
            text_tokens = cls._tokens(candidate.searchable_text)
            alias_tokens = [cls._tokens(alias) for alias in candidate.aliases]
            exact_alias = any(query <= alias for alias in alias_tokens if alias)
            exact_name = bool(name_tokens and (query <= name_tokens or name_tokens <= query))
            descriptive = query <= text_tokens
            if exact_alias or exact_name:
                matches.append((candidate, "canonical_name", 100))
            elif descriptive:
                matches.append((candidate, "description", 55))
        return tuple(sorted(matches, key=lambda item: (-item[2], item[0].name.casefold(), str(item[0].referent_id))))

    @classmethod
    def _history_candidates(
        cls,
        candidates: tuple[_WorldReferent, ...],
        recent_turns: Iterable[object],
        *,
        current_input: str = "",
    ) -> dict[tuple[WorldReferenceCategory, int | str], tuple[DiscourseEvidence, ...]]:
        evidence: dict[tuple[WorldReferenceCategory, int | str], list[DiscourseEvidence]] = {}
        turns = list(
            DiscourseContextBuilder.scope_history(recent_turns, current_input)
        )[-cls.MAX_HISTORY_TURNS :]
        for recency_rank, turn in enumerate(reversed(turns), start=1):
            parts, turn_id = cls._turn_parts(turn)
            for candidate in candidates:
                for text, source, speaker in parts:
                    normalized_text = cls._tokens(text)
                    found = None
                    for alias in candidate.aliases:
                        alias_tokens = cls._tokens(alias)
                        if not alias_tokens:
                            continue
                        if alias_tokens <= normalized_text:
                            found = alias
                            break
                        # Keep evidence literal even when the transcript uses
                        # a shortened form of a longer canonical item name.
                        shared_tokens = sorted(alias_tokens & normalized_text)
                        if shared_tokens:
                            found = shared_tokens[0]
                            break
                    if found is None:
                        continue
                    key = (candidate.category, candidate.referent_id)
                    evidence.setdefault(key, []).append(
                        DiscourseEvidence(
                            turn_id=turn_id,
                            source=source,
                            speaker=speaker,
                            mention=found[:120],
                            excerpt=text,
                            recency_rank=recency_rank,
                        )
                    )
        return {key: tuple(values) for key, values in evidence.items()}

    @staticmethod
    def _score(evidence: tuple[DiscourseEvidence, ...]) -> tuple[int, tuple[str, ...]]:
        best_rank = min(item.recency_rank for item in evidence)
        score = max(15, 70 - (best_rank - 1) * 5)
        signals = ["recency"]
        if any(item.source is DiscourseSource.PLAYER_INPUT for item in evidence):
            score += 22
            signals.append("player_authored_focus")
        else:
            score += 8
            signals.append("narrator_context")
        distinct_turns = {item.turn_id for item in evidence if item.turn_id is not None}
        repeat_bonus = min(15, max(0, len(distinct_turns) - 1) * 5)
        if repeat_bonus:
            score += repeat_bonus
            signals.append("topic_continuity")
        return min(1000, score), tuple(signals)

    @staticmethod
    def _question(mention: str, candidates: tuple[str, ...]) -> str:
        safe = mention.strip()[:90]
        if candidates:
            return f"¿A qué referente te refieres con «{safe}»: {', '.join(candidates[:4])}?"[:300]
        return f"¿A qué objeto, recurso o acontecimiento te refieres con «{safe}»?"[:300]

    def resolve(
        self,
        visible_world: WorldState,
        analysis: PlayerIntentAnalysis,
        *,
        recent_turns=(),
        character_entity_id: int | None = None,
        current_input: str | None = None,
    ) -> WorldReferenceResolution:
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
        if character_entity_id is not None and (
            isinstance(character_entity_id, bool)
            or not isinstance(character_entity_id, int)
            or character_entity_id < 1
        ):
            raise ValueError("character_entity_id must be a positive integer or None")
        if not analysis.allows_world_proposal:
            return WorldReferenceResolution()

        grouped = self._collect(visible_world, character_entity_id=character_entity_id)
        history: dict[tuple[WorldReferenceCategory, int | str], tuple[DiscourseEvidence, ...]] = {}
        discourse_input = current_input or (
            analysis.steps[
                analysis.active_step_index
                if analysis.active_step_index is not None
                else len(analysis.steps) - 1
            ].source_excerpt
            if analysis.steps
            else ""
        )
        for values in grouped.values():
            history.update(
                self._history_candidates(
                    values,
                    recent_turns,
                    current_input=discourse_input,
                )
            )

        last_step = analysis.active_step_index if analysis.active_step_index is not None else len(analysis.steps) - 1
        mentions: list[tuple[str, SemanticObjectKind]] = []
        for step in analysis.steps[: last_step + 1]:
            if step.polarity is not IntentPolarity.POSITIVE or step.modality not in self._ELIGIBLE_STEP_MODALITIES:
                continue
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
                for mention in (claim.subject, claim.object)
            )

        typed_mentions: dict[str, tuple[str, set[WorldReferenceCategory]]] = {}
        for mention, kind_hint in mentions:
            category = self._KIND_CATEGORY.get(kind_hint)
            if category is None:
                continue
            mention_key = self._normalize(mention)
            if not mention_key:
                continue
            current = typed_mentions.get(mention_key)
            if current is None:
                typed_mentions[mention_key] = (mention, {category})
            else:
                current[1].add(category)

        references: list[ResolvedWorldReference] = []
        seen: set[tuple[WorldReferenceCategory, int | str, str]] = set()
        for mention_key, (mention, categories) in typed_mentions.items():
            if len(categories) > 1:
                return WorldReferenceResolution(
                    tuple(references),
                    self._question(mention, ()),
                    "semantic_kind_conflict",
                )
            category = next(iter(categories))
            candidates = grouped[category]
            explicit = self._explicit_matches(mention, candidates)
            selected: _WorldReferent | None = None
            match_kind = "explicit"
            selected_evidence: tuple[DiscourseEvidence, ...] = ()
            confidence = 0
            signals: tuple[str, ...] = ()

            # Demonstratives and "same object" phrases carry a lexical head;
            # use that head before attempting cross-turn ranking.
            if explicit and (not self._is_anaphoric(mention) or self._has_lexical_head(mention)):
                top_score = explicit[0][2]
                top = [item for item in explicit if item[2] == top_score]
                if len(top) > 1:
                    names = tuple(dict.fromkeys(item[0].name for item in top))
                    return WorldReferenceResolution(
                        tuple(references),
                        self._question(mention, names),
                        "explicit_world_reference_ambiguous",
                        names,
                    )
                selected, match_kind, confidence = explicit[0]
                signals = ("typed_explicit_match",)
            elif self._is_anaphoric(mention):
                ranked = []
                pronoun_features = DiscourseContextBuilder.pronoun_agreement(mention)
                for candidate in candidates:
                    candidate_evidence = history.get((candidate.category, candidate.referent_id), ())
                    if not candidate_evidence:
                        continue
                    if pronoun_features is not None:
                        gender, number = pronoun_features
                        if number == "plural":
                            # A single physical instance/resource/event is not
                            # a canonical group identity.
                            continue
                        observed_features = {
                            DiscourseContextBuilder.grammatical_features(
                                item.excerpt,
                                alias,
                            )
                            for item in candidate_evidence
                            for alias in candidate.aliases
                        }
                        observed_features.discard((None, None))
                        if observed_features and (gender, number) not in observed_features:
                            continue
                    score, candidate_signals = self._score(candidate_evidence)
                    ranked.append((candidate, score, candidate_signals, candidate_evidence))
                ranked.sort(key=lambda item: (-item[1], item[0].name.casefold(), str(item[0].referent_id)))
                if not ranked:
                    return WorldReferenceResolution(
                        tuple(references),
                        self._question(mention, ()),
                        "no_visible_typed_antecedent",
                    )
                best = ranked[0]
                second_score = ranked[1][1] if len(ranked) > 1 else 0
                if best[1] < self.MIN_RESOLUTION_SCORE or (
                    len(ranked) > 1 and best[1] - second_score < self.MIN_RESOLUTION_MARGIN
                ):
                    names = tuple(dict.fromkeys(item[0].name for item in ranked))
                    return WorldReferenceResolution(
                        tuple(references),
                        self._question(mention, names),
                        "typed_discourse_candidates_ambiguous",
                        names,
                    )
                selected, confidence, signals, selected_evidence = best[0], best[1], best[2], best[3]
                match_kind = "typed_conversation_antecedent"
            else:
                # A genuinely new proper name or an unrelated argument is not a
                # failed reference resolution and remains available to creation logic.
                continue

            if selected is None:
                continue
            key = (selected.category, selected.referent_id, mention_key)
            if key in seen:
                continue
            antecedent_turn_id = next(
                (
                    item.turn_id for item in selected_evidence
                    if item.turn_id is not None
                    and item.recency_rank == min(value.recency_rank for value in selected_evidence)
                ),
                None,
            )
            references.append(
                ResolvedWorldReference(
                    mention=mention,
                    category=selected.category,
                    referent_id=selected.referent_id,
                    name=selected.name,
                    match_kind=match_kind,
                    antecedent_turn_id=antecedent_turn_id,
                    evidence=selected_evidence,
                    confidence_score=confidence,
                    resolution_signals=signals,
                )
            )
            seen.add(key)
            if len(references) >= self.MAX_REFERENCES:
                break
        return WorldReferenceResolution(tuple(references))
