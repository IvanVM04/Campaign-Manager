"""Conservative, evidence-producing coreference resolution over a chat-scoped transcript."""

from __future__ import annotations

import re
from dataclasses import dataclass

from models.discourse_evidence import (
    ConversationReferenceMention,
    DiscourseCandidate,
    DiscourseCandidateRanking,
    DiscourseEvidence,
    DiscourseMentionOrigin,
    DiscourseSource,
    DiscourseSpeaker,
)
from models.entity import Entity
from models.player_intent_analysis import (
    IntentModality,
    PlayerIntentAnalysis,
)
from models.resolved_conversation_reference import (
    ResolvedConversationGroupReference,
    ResolvedConversationReference,
    ResolvedConversationReferenceResult,
)
from models.semantic_frames import SemanticObjectKind
from models.world_state import WorldState
from services.discourse_context import (
    DiscourseContextBuilder,
    SurfacePronounMention,
)

from .conversation_reference_evidence import ConversationReferenceEvidenceExtractor
from .conversation_reference_ranker import ConversationReferenceCandidateRanker
from .entity_reference_resolver import EntityReferenceResolver


@dataclass(frozen=True, slots=True)
class ConversationReferenceResolution:
    references: tuple[ResolvedConversationReferenceResult, ...] = ()
    clarification_question: str | None = None
    candidates: tuple[DiscourseCandidate, ...] = ()
    abstention_reason: str | None = None
    ranking_diagnostics: tuple[DiscourseCandidateRanking, ...] = ()


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
    # Resolving a mention is an interpretation aid, not permission to
    # adjudicate mechanics or propose a persistent world change. Include
    # referential questions and future/conditional utterances as well as
    # actionable and reported steps; downstream stages keep their own gates.
    _ELIGIBLE_MODALITIES = frozenset({
        IntentModality.ATTEMPTED,
        IntentModality.COMPLETED,
        IntentModality.OBSERVED,
        IntentModality.REPORTED,
        IntentModality.CORRECTION,
        IntentModality.DIALOGUE,
        IntentModality.QUESTION,
        IntentModality.PLANNED,
        IntentModality.CONDITIONAL,
        IntentModality.NEGATED,
    })
    MIN_RESOLUTION_SCORE = 35
    MIN_RESOLUTION_MARGIN = 12
    MAX_HISTORY_TURNS = DiscourseContextBuilder.MAX_HISTORY_TURNS

    def __init__(self, entity_resolver: EntityReferenceResolver | None = None) -> None:
        if entity_resolver is not None and not isinstance(entity_resolver, EntityReferenceResolver):
            raise TypeError("entity_resolver must be an EntityReferenceResolver or None")
        self.entity_resolver = entity_resolver or EntityReferenceResolver()
        self.evidence_extractor = ConversationReferenceEvidenceExtractor(
            self.entity_resolver
        )
        self.candidate_ranker = ConversationReferenceCandidateRanker()

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
        return ConversationReferenceEvidenceExtractor.turn_parts(turn, world)

    @staticmethod
    def _visible_entities(world: WorldState) -> tuple[Entity, ...]:
        return ConversationReferenceEvidenceExtractor.visible_entities(world)

    def _kind_compatible(
        self,
        entity: Entity,
        kind_hint: SemanticObjectKind,
    ) -> bool | None:
        return self.candidate_ranker.kind_compatible(entity, kind_hint)

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
        return self.evidence_extractor.mentions_in_part(
            entity,
            text,
            turn_id=turn_id,
            source=source,
            speaker=speaker,
            recency_rank=recency_rank,
            speaker_entity_id=speaker_entity_id,
        )

    def _history_evidence(
        self,
        world: WorldState,
        recent_turns,
        *,
        current_input: str,
    ) -> dict[int, tuple[DiscourseEvidence, ...]]:
        bundle = self.evidence_extractor.extract(
            world,
            recent_turns,
            current_input=current_input,
        )
        return {
            item.entity_id: item.evidence
            for item in bundle.entity_evidence
        }

    def _candidate_score(
        self,
        evidence: tuple[DiscourseEvidence, ...],
        *,
        kind_hint: SemanticObjectKind,
        entity,
    ) -> tuple[int, tuple[str, ...]]:
        return self.candidate_ranker.candidate_score(
            evidence,
            kind_hint=kind_hint,
            entity=entity,
        )

    def _rank_candidates(
        self,
        world: WorldState,
        recent_turns,
        *,
        kind_hint: SemanticObjectKind,
        mention: str,
        current_input: str,
    ) -> tuple[DiscourseCandidate, ...]:
        bundle = self.evidence_extractor.extract(
            world,
            recent_turns,
            current_input=current_input,
        )
        return self.candidate_ranker.rank(
            bundle,
            world,
            kind_hint=kind_hint,
            mention=mention,
        ).candidates

    @classmethod
    def _group_reference_from_candidates(
        cls,
        mention: str,
        ranked: tuple[DiscourseCandidate, ...],
    ) -> tuple[ResolvedConversationGroupReference | None, str | None]:
        return ConversationReferenceCandidateRanker.group_reference_from_candidates(
            mention,
            ranked,
        )

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

    def _extract_step_mentions(
        self,
        step,
        relation_claims,
        visible_world: WorldState,
    ) -> tuple[
        tuple[ConversationReferenceMention, ...],
        set[str],
        dict[str, set[SemanticObjectKind]],
    ]:
        """Extract current-step mentions while retaining all backend-observed origins."""
        specs: list[
            tuple[
                str,
                SemanticObjectKind,
                DiscourseMentionOrigin,
                int | None,
                int | None,
            ]
        ] = [
            (
                mention,
                SemanticObjectKind.UNKNOWN,
                DiscourseMentionOrigin.TARGET_MENTION,
                None,
                None,
            )
            for mention in step.target_mentions
        ]
        if step.attributed_to is not None:
            specs.append((
                step.attributed_to,
                SemanticObjectKind.CHARACTER,
                DiscourseMentionOrigin.ATTRIBUTION,
                None,
                None,
            ))
        if step.action_frame is not None:
            specs.extend(
                (
                    argument.mention.text,
                    argument.mention.kind_hint,
                    DiscourseMentionOrigin.ACTION_ARGUMENT,
                    None,
                    None,
                )
                for argument in step.action_frame.arguments
            )

        surface_mentions = DiscourseContextBuilder.surface_pronoun_mentions(
            step.source_excerpt
        )
        explicit_recipients = [item[0] for item in specs]
        explicit_recipients.extend(
            surface.text
            for surface in surface_mentions
            if surface.text.casefold() not in {"le", "les"}
        )
        for entity in self._visible_entities(visible_world):
            explicit_recipients.append(entity.name)
            aliases = getattr(entity, "aliases", [])
            if isinstance(aliases, (list, tuple)):
                explicit_recipients.extend(
                    alias for alias in aliases if isinstance(alias, str)
                )

        specs.extend(
            (
                surface.text,
                SemanticObjectKind.CHARACTER,
                DiscourseMentionOrigin.SURFACE_PRONOUN,
                surface.start,
                surface.end,
            )
            for surface in surface_mentions
            if not self._has_explicit_dative_complement(
                step.source_excerpt,
                surface,
                tuple(explicit_recipients),
            )
        )
        specs.extend(
            (
                mention.text,
                mention.kind_hint,
                DiscourseMentionOrigin.RELATION_ENDPOINT,
                None,
                None,
            )
            for claim in relation_claims
            if claim.step_index == step.index
            for mention in (
                claim.subject,
                claim.object,
                *((claim.attributed_to,) if claim.attributed_to is not None else ()),
            )
        )

        # The tuple layout is fixed and typed; only the origin accumulator mutates.
        merged: dict[
            str,
            tuple[
                str,
                SemanticObjectKind,
                list[DiscourseMentionOrigin],
                int | None,
                int | None,
            ],
        ] = {}
        conflicting_kinds: set[str] = set()
        conflicting_kind_values: dict[str, set[SemanticObjectKind]] = {}

        for text, kind_hint, origin, start_offset, end_offset in specs:
            mention_key = self.entity_resolver.normalize(text)
            if not mention_key:
                continue
            existing = merged.get(mention_key)
            if existing is None:
                merged[mention_key] = (
                    text,
                    kind_hint,
                    [origin],
                    start_offset,
                    end_offset,
                )
                continue

            existing_text, existing_kind, origins, existing_start, existing_end = existing
            origins.append(origin)
            if existing_start is None and start_offset is not None:
                existing_start, existing_end = start_offset, end_offset

            if existing_kind is SemanticObjectKind.UNKNOWN:
                if mention_key in conflicting_kinds:
                    if kind_hint is not SemanticObjectKind.UNKNOWN:
                        conflicting_kind_values.setdefault(
                            mention_key,
                            set(),
                        ).add(kind_hint)
                else:
                    existing_kind = kind_hint
            elif (
                kind_hint is not SemanticObjectKind.UNKNOWN
                and kind_hint is not existing_kind
            ):
                conflicting_kind_values.setdefault(
                    mention_key,
                    {existing_kind, kind_hint},
                ).update({existing_kind, kind_hint})
                existing_kind = SemanticObjectKind.UNKNOWN
                conflicting_kinds.add(mention_key)

            merged[mention_key] = (
                existing_text,
                existing_kind,
                origins,
                existing_start,
                existing_end,
            )

        typed_mentions = tuple(
            ConversationReferenceMention(
                text=text,
                step_index=step.index,
                kind_hint=kind_hint,
                origins=tuple(dict.fromkeys(origins)),
                start_offset=start_offset,
                end_offset=end_offset,
            )
            for (
                text,
                kind_hint,
                origins,
                start_offset,
                end_offset,
            ) in merged.values()
        )
        return typed_mentions, conflicting_kinds, conflicting_kind_values

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

    @staticmethod
    def _has_explicit_dative_complement(
        source_excerpt: str,
        mention: SurfacePronounMention,
        explicit_recipients: tuple[str, ...],
    ) -> bool:
        """Coalesce a clitic only when its clause names the same recipient."""
        if mention.text.casefold() not in {"le", "les"}:
            return False
        following = source_excerpt[mention.end : mention.end + 180]
        clause = re.split(r"[,;.!?:]", following, maxsplit=1)[0]
        candidate_keys: set[str] = set()
        articles = {"el", "la", "los", "las", "un", "una", "unos", "unas"}

        def normalized_complement(value: str) -> str:
            tokens = EntityReferenceResolver.normalize(value).split()
            # The accent in tonic "él" is removed by normalization. Preserve
            # that pronoun before stripping leading articles, or "a él" becomes
            # indistinguishable from an article-led noun phrase.
            first_raw_tokens = value.strip().split(maxsplit=1)
            first_raw_token = (
                first_raw_tokens[0].strip(".,;:!?¿¡()[]{}\"'")
                if first_raw_tokens
                else ""
            )
            is_tonic_pronoun = first_raw_token.casefold() == "él"
            if not is_tonic_pronoun:
                while tokens and tokens[0] in articles:
                    tokens.pop(0)
            return " ".join(tokens)

        for candidate in explicit_recipients:
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            normalized = normalized_complement(candidate)
            if normalized:
                candidate_keys.add(normalized)

        # Search every a/al complement rather than treating adverbials such as
        # "a menudo" or "a veces" as a person reference.
        for match in re.finditer(r"(?<!\w)(?:al|a)\s+", clause, flags=re.IGNORECASE):
            raw_recipient = clause[match.end():]
            normalized_recipient = normalized_complement(raw_recipient)
            if any(
                normalized_recipient == candidate
                or normalized_recipient.startswith(candidate + " ")
                for candidate in candidate_keys
            ):
                return True
            # A capitalized proper name is explicit even if the campaign does
            # not currently contain that entity. Common lowercase adverbials
            # and role descriptions do not take this fallback.
            raw_first = raw_recipient.lstrip().split(maxsplit=1)
            if raw_first and raw_first[0][:1].isupper():
                return True
        return False

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
        # Do not gate reference understanding on world-write eligibility.
        # A report/dialogue/question can contain an important anaphoric mention
        # even when it must never produce a persistent proposal. This resolver
        # only returns evidence-backed references or clarification requests;
        # TurnResolutionService and the proposal stage retain write authorization.
        last_step = (
            analysis.active_step_index
            if analysis.active_step_index is not None
            else len(analysis.steps) - 1
        )
        references: list[ResolvedConversationReferenceResult] = []
        ranking_diagnostics: list[DiscourseCandidateRanking] = []
        seen: set[tuple[str, tuple[int, ...]]] = set()

        for step in analysis.steps[: last_step + 1]:
            # This is read-only reference comprehension. Negative or uncertain
            # language still needs its entities resolved for narration and
            # clarification; polarity/modality write rules remain downstream.
            if step.modality not in self._ELIGIBLE_MODALITIES:
                continue
            typed_mentions, _conflicting_kinds, conflicting_kind_values = (
                self._extract_step_mentions(
                    step,
                    analysis.relation_claims,
                    visible_world,
                )
            )
            evidence_bundle = self.evidence_extractor.extract(
                visible_world,
                recent_turns,
                current_input=current_input or step.source_excerpt,
                mentions=typed_mentions,
            )

            for mention_record in evidence_bundle.mentions:
                mention = mention_record.text
                mention_key = self.entity_resolver.normalize(mention)
                kind_hint = mention_record.kind_hint
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

                pronoun_features = DiscourseContextBuilder.pronoun_agreement(mention)
                if (
                    not candidate_ids
                    and self._is_anaphoric(mention)
                    and pronoun_features is not None
                    and pronoun_features[1] == "plural"
                ):
                    ranking = self.candidate_ranker.rank(
                        evidence_bundle,
                        visible_world,
                        kind_hint=SemanticObjectKind.CHARACTER,
                        mention=mention,
                    )
                    ranking_diagnostics.append(ranking)
                    ranked = ranking.candidates
                    group_reference, group_abstention_reason = (
                        self.candidate_ranker.group_reference_from_candidates(
                            mention,
                            ranked,
                        )
                    )
                    if group_reference is None:
                        names = self._candidate_names(ranked)
                        return ConversationReferenceResolution(
                            tuple(references),
                            self._question(mention, names),
                            candidates=ranked[:4],
                            abstention_reason=(
                                group_abstention_reason or ranking.abstention_reason
                                or "plural_group_not_proven"
                            ),
                            ranking_diagnostics=tuple(ranking_diagnostics),
                        )
                    group_key = (
                        self.entity_resolver.normalize(mention),
                        group_reference.entity_ids,
                    )
                    if group_key not in seen:
                        references.append(group_reference)
                        seen.add(group_key)
                    continue

                if not candidate_ids and self._is_anaphoric(mention):
                    ranking = self.candidate_ranker.rank(
                        evidence_bundle,
                        visible_world,
                        kind_hint=kind_hint,
                        mention=mention,
                    )
                    ranking_diagnostics.append(ranking)
                    ranked = ranking.candidates
                    is_other_role = any(
                        token in self._OTHER_MARKERS
                        for token in self._tokens(mention)
                    )

                    if is_other_role:
                        antecedent = ranking.selected_candidate
                        if antecedent is None:
                            reason = (
                                "other_role_antecedent_ambiguous"
                                if ranking.status.value == "ambiguous_margin"
                                else "other_role_antecedent_not_established"
                            )
                            return ConversationReferenceResolution(
                                tuple(references),
                                self._question(
                                    mention,
                                    self._candidate_names(ranked),
                                ),
                                candidates=ranked[:4],
                                abstention_reason=reason,
                                ranking_diagnostics=tuple(ranking_diagnostics),
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
                        role_ranking = self.candidate_ranker.evaluate(
                            mention,
                            tuple(role_candidates),
                        )
                        ranking_diagnostics.append(role_ranking)
                        selected = role_ranking.selected_candidate
                        if selected is None:
                            reason = (
                                "other_role_antecedent_ambiguous"
                                if role_ranking.status.value == "ambiguous_margin"
                                else "other_role_antecedent_not_established"
                            )
                            return ConversationReferenceResolution(
                                tuple(references),
                                self._question(
                                    mention,
                                    self._candidate_names(role_ranking.candidates),
                                ),
                                candidates=role_ranking.candidates[:4],
                                abstention_reason=reason,
                                ranking_diagnostics=tuple(ranking_diagnostics),
                            )
                        ranked = role_ranking.candidates
                        match_kind = "other_role_in_conversation"
                    else:
                        selected = ranking.selected_candidate
                        match_kind = "conversation_antecedent"
                        if selected is None:
                            return ConversationReferenceResolution(
                                tuple(references),
                                self._question(
                                    mention,
                                    self._candidate_names(ranked),
                                ),
                                candidates=ranked[:4],
                                abstention_reason=(
                                    ranking.abstention_reason
                                    or "no_visible_antecedent_evidence"
                                ),
                                ranking_diagnostics=tuple(ranking_diagnostics),
                            )

                    candidate_ids = (selected.entity_id,)
                    selected_evidence = selected.evidence
                    selected_score = selected.score
                    signals = selected.signals
                    selected_turn_id = next(
                        (
                            item.turn_id
                            for item in selected.evidence
                            if item.turn_id is not None
                            and item.recency_rank == min(
                                evidence.recency_rank
                                for evidence in selected.evidence
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
                key = (self.entity_resolver.normalize(mention), (entity_id,))
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

        return ConversationReferenceResolution(
            tuple(references),
            ranking_diagnostics=tuple(ranking_diagnostics),
        )
