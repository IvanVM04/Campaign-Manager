"""Rank bounded conversation-reference candidates and enforce abstention gates."""

from __future__ import annotations

from models.discourse_evidence import (
    CandidateRankingStatus,
    DiscourseCandidate,
    DiscourseCandidateRanking,
    DiscourseEvidence,
    DiscourseEvidenceBundle,
    DiscourseSource,
    DiscourseSpeaker,
)
from models.entity import Entity
from models.resolved_conversation_reference import (
    ResolvedConversationGroupMember,
    ResolvedConversationGroupReference,
)
from models.semantic_frames import SemanticObjectKind
from models.world_state import WorldState
from services.discourse_context import DiscourseContextBuilder
from typing import ClassVar

from models.discourse_evidence import (
    CandidateRankingStatus,
    DiscourseCandidate,
    DiscourseCandidateRanking,
    DiscourseEvidence,
    DiscourseEvidenceBundle,
    DiscourseSource,
    DiscourseSpeaker,
)
from models.entity import Entity
from models.resolved_conversation_reference import (
    ResolvedConversationGroupMember,
    ResolvedConversationGroupReference,
)
from models.semantic_frames import SemanticObjectKind
from models.world_state import WorldState
from services.discourse_context import DiscourseContextBuilder

from .entity_reference_resolver import EntityReferenceResolver


class ConversationReferenceCandidateRanker:
    """Rank only evidence records in a prebuilt, visibility-filtered bundle."""

    MIN_RESOLUTION_SCORE = 35
    MIN_RESOLUTION_MARGIN = 12
    MAX_GROUP_MEMBERS = 8
    _KIND_TYPES: ClassVar[dict[SemanticObjectKind, frozenset[str]]] = {
        SemanticObjectKind.CHARACTER: frozenset({
            "npc", "character", "person", "humanoid", "player",
        }),
        SemanticObjectKind.CREATURE: frozenset({
            "creature", "monster", "beast", "animal",
        }),
        SemanticObjectKind.LOCATION: frozenset({
            "location", "place", "room", "building", "area",
        }),
        SemanticObjectKind.FACTION: frozenset({
            "faction", "guild", "organization", "group",
        }),
        SemanticObjectKind.RESOURCE: frozenset({
            "resource", "currency", "consumable",
        }),
    }

    def kind_compatible(
        self,
        entity: Entity,
        kind_hint: SemanticObjectKind,
    ) -> bool | None:
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

    def candidate_score(
        self,
        evidence: tuple[DiscourseEvidence, ...],
        *,
        kind_hint: SemanticObjectKind,
        entity: Entity,
    ) -> tuple[int, tuple[str, ...]]:
        score = 0
        signals: list[str] = []
        best_rank = min(item.recency_rank for item in evidence)
        score += max(15, 70 - (best_rank - 1) * 12)
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
        distinct_turns = {
            item.turn_id for item in evidence if item.turn_id is not None
        }
        repeat_bonus = min(15, max(0, len(distinct_turns) - 1) * 5)
        if repeat_bonus:
            score += repeat_bonus
            signals.append("topic_continuity")
        kind_match = self.kind_compatible(entity, kind_hint)
        if kind_match is True:
            score += 24
            signals.append("semantic_kind_match")
        elif kind_match is False:
            signals.append("semantic_kind_mismatch")
        return min(1000, score), tuple(signals)

    def rank(
        self,
        bundle: DiscourseEvidenceBundle,
        world: WorldState,
        *,
        mention: str,
        kind_hint: SemanticObjectKind,
        minimum_score: int | None = None,
        minimum_margin: int | None = None,
    ) -> DiscourseCandidateRanking:
        """Return sorted candidates and an explicit score/margin decision."""
        if not isinstance(bundle, DiscourseEvidenceBundle):
            raise TypeError("bundle must be a DiscourseEvidenceBundle")
        if not isinstance(world, WorldState):
            raise TypeError("world must be a WorldState")
        if not isinstance(mention, str) or not mention.strip():
            raise ValueError("mention must be non-empty text")
        if not isinstance(kind_hint, SemanticObjectKind):
            raise TypeError("kind_hint must be a SemanticObjectKind")

        score_floor = (
            self.MIN_RESOLUTION_SCORE if minimum_score is None else minimum_score
        )
        margin_floor = (
            self.MIN_RESOLUTION_MARGIN if minimum_margin is None else minimum_margin
        )
        candidates: list[DiscourseCandidate] = []
        pronoun_features = DiscourseContextBuilder.pronoun_agreement(mention)

        for entity in world.entities.values():
            if not isinstance(entity, Entity) or not entity.active:
                continue
            entity_id = entity.id
            if (
                isinstance(entity_id, bool)
                or not isinstance(entity_id, int)
                or entity_id < 1
            ):
                continue
            evidence = bundle.evidence_for(entity_id)
            if not evidence:
                continue
            if self.kind_compatible(entity, kind_hint) is False:
                continue

            if pronoun_features is not None:
                gender, number = pronoun_features
                observed_features = {
                    DiscourseContextBuilder.grammatical_features(
                        item.excerpt,
                        alias,
                    )
                    for item in evidence
                    for alias in (
                        getattr(entity, "name", ""),
                        *(getattr(entity, "aliases", []) or []),
                    )
                    if isinstance(alias, str) and alias.strip()
                }
                observed_features.discard((None, None))
                if number == "plural":
                    if not any(
                        number_seen == "singular"
                        and (gender == "unknown" or gender_seen == gender)
                        for gender_seen, number_seen in observed_features
                    ):
                        continue
                elif (
                    gender != "unknown"
                    and observed_features
                    and (gender, number) not in observed_features
                ):
                    continue

            score, signals = self.candidate_score(
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

        ranked = tuple(sorted(
            candidates,
            key=lambda item: (-item.score, item.entity_id),
        ))
        return self.evaluate(
            mention,
            ranked,
            minimum_score=score_floor,
            minimum_margin=margin_floor,
        )

    def evaluate(
        self,
        mention: str,
        candidates: tuple[DiscourseCandidate, ...],
        *,
        minimum_score: int | None = None,
        minimum_margin: int | None = None,
    ) -> DiscourseCandidateRanking:
        """Apply the single score/margin contract to any deterministic candidate set."""
        score_floor = (
            self.MIN_RESOLUTION_SCORE if minimum_score is None else minimum_score
        )
        margin_floor = (
            self.MIN_RESOLUTION_MARGIN if minimum_margin is None else minimum_margin
        )
        ranked = tuple(sorted(
            candidates,
            key=lambda item: (-item.score, item.entity_id),
        ))
        if not ranked:
            status = CandidateRankingStatus.NO_CANDIDATES
        elif ranked[0].score < score_floor:
            status = CandidateRankingStatus.BELOW_MINIMUM_SCORE
        elif (
            len(ranked) > 1
            and ranked[0].score - ranked[1].score < margin_floor
        ):
            status = CandidateRankingStatus.AMBIGUOUS_MARGIN
        else:
            status = CandidateRankingStatus.RESOLVED
        return DiscourseCandidateRanking(
            mention=mention,
            candidates=ranked,
            minimum_score=score_floor,
            minimum_margin=margin_floor,
            status=status,
        )

    @classmethod
    def group_reference_from_candidates(
        cls,
        mention: str,
        ranked: tuple[DiscourseCandidate, ...],
    ) -> tuple[ResolvedConversationGroupReference | None, str | None]:
        """Build a bounded group only from same-source, same-turn co-mention."""
        features = DiscourseContextBuilder.pronoun_agreement(mention)
        if features is None or features[1] != "plural":
            return None, "plural_group_not_proven"
        gender = features[0]
        buckets: dict[
            tuple[int, DiscourseSource, DiscourseSpeaker, str, int],
            dict[int, tuple[DiscourseCandidate, DiscourseEvidence]],
        ] = {}
        for candidate in ranked:
            for evidence in candidate.evidence:
                if evidence.turn_id is None:
                    continue
                grammatical = DiscourseContextBuilder.grammatical_features(
                    evidence.excerpt,
                    evidence.mention,
                )
                if (
                    grammatical is None
                    or grammatical[1] != "singular"
                    or (gender != "unknown" and grammatical[0] != gender)
                ):
                    continue
                key = (
                    evidence.turn_id,
                    evidence.source,
                    evidence.speaker,
                    evidence.excerpt,
                    evidence.recency_rank,
                )
                buckets.setdefault(key, {})[candidate.entity_id] = (
                    candidate,
                    evidence,
                )

        eligible = [
            (key, members)
            for key, members in buckets.items()
            if 2 <= len(members) <= cls.MAX_GROUP_MEMBERS
        ]
        if not eligible:
            return None, "plural_group_not_proven"
        most_recent_rank = min(key[4] for key, _members in eligible)
        most_recent = [
            (key, members)
            for key, members in eligible
            if key[4] == most_recent_rank
        ]
        if len(most_recent) != 1:
            return None, "plural_group_ambiguous"

        key, selected_members = most_recent[0]
        members = tuple(
            ResolvedConversationGroupMember(
                entity_id=candidate.entity_id,
                entity_name=candidate.entity_name,
                evidence=(evidence,),
                confidence_score=candidate.score,
                resolution_signals=tuple(dict.fromkeys(
                    (
                        *candidate.signals,
                        "plural_group_co_mention",
                        "explicit_grammatical_agreement",
                    )
                )),
            )
            for candidate, evidence in sorted(
                selected_members.values(),
                key=lambda pair: pair[0].entity_id,
            )
        )
        return (
            ResolvedConversationGroupReference(
                mention=mention,
                members=members,
                antecedent_turn_id=key[0],
            ),
            None,
        )
