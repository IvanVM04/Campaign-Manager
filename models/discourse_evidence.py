"""Typed, application-produced evidence for cross-turn discourse resolution."""

from __future__ import annotations

import enum
import re
import unicodedata
from dataclasses import dataclass

from models.semantic_frames import SemanticObjectKind

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class DiscourseSource(str, enum.Enum):
    PLAYER_INPUT = "player_input"
    NARRATIVE = "narrative"


class DiscourseSpeaker(str, enum.Enum):
    PLAYER = "player"
    NARRATOR = "narrator"
    NPC = "npc"


@dataclass(frozen=True, slots=True)
class DiscourseEvidence:
    """One literal antecedent occurrence from an already scoped transcript turn."""

    turn_id: int | None
    source: DiscourseSource
    speaker: DiscourseSpeaker
    mention: str
    excerpt: str
    recency_rank: int
    speaker_entity_id: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None

    def __post_init__(self) -> None:
        if self.turn_id is not None and (
            isinstance(self.turn_id, bool)
            or not isinstance(self.turn_id, int)
            or self.turn_id < 1
        ):
            raise ValueError("turn_id must be a positive integer or None")
        if not isinstance(self.source, DiscourseSource):
            raise TypeError("source must be a DiscourseSource")
        if not isinstance(self.speaker, DiscourseSpeaker):
            raise TypeError("speaker must be a DiscourseSpeaker")
        _validate_text(self.mention, "mention", 120)
        _validate_text(self.excerpt, "excerpt", 1200)
        if (
            isinstance(self.recency_rank, bool)
            or not isinstance(self.recency_rank, int)
            or not 1 <= self.recency_rank <= 12
        ):
            raise ValueError("recency_rank must be between 1 and 12")
        if self.speaker_entity_id is not None and (
            isinstance(self.speaker_entity_id, bool)
            or not isinstance(self.speaker_entity_id, int)
            or self.speaker_entity_id < 1
        ):
            raise ValueError("speaker_entity_id must be a positive integer or None")
        if self.speaker is DiscourseSpeaker.NPC and self.speaker_entity_id is None:
            raise ValueError("NPC discourse evidence requires an explicit speaker entity id")
        if self.speaker is not DiscourseSpeaker.NPC and self.speaker_entity_id is not None:
            raise ValueError("speaker_entity_id is only valid for NPC discourse evidence")
        if not _contains_literal(self.excerpt, self.mention):
            raise ValueError("mention must occur in its evidence excerpt")
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("evidence offsets must both be present or both be None")
        if self.start_offset is not None and (
            isinstance(self.start_offset, bool)
            or not isinstance(self.start_offset, int)
            or isinstance(self.end_offset, bool)
            or not isinstance(self.end_offset, int)
            or self.start_offset < 0
            or self.end_offset <= self.start_offset
            or self.end_offset > len(self.excerpt)
            or self.excerpt[self.start_offset:self.end_offset].casefold()
            != self.mention.casefold()
        ):
            raise ValueError("evidence offsets must identify the literal mention")


@dataclass(frozen=True, slots=True)
class DiscourseCandidate:
    """A visible canonical entity supported by typed transcript evidence."""

    entity_id: int
    entity_name: str
    score: int
    evidence: tuple[DiscourseEvidence, ...]
    signals: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.entity_id, bool)
            or not isinstance(self.entity_id, int)
            or self.entity_id < 1
        ):
            raise ValueError("entity_id must be a positive integer")
        _validate_text(self.entity_name, "entity_name", 120)
        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, int)
            or not 0 <= self.score <= 1000
        ):
            raise ValueError("score must be an integer between 0 and 1000")
        if not isinstance(self.evidence, tuple) or not self.evidence:
            raise ValueError("evidence must be a non-empty tuple")
        if any(not isinstance(item, DiscourseEvidence) for item in self.evidence):
            raise TypeError("evidence must contain DiscourseEvidence values")
        if not isinstance(self.signals, tuple) or any(
            not isinstance(item, str) or not item.strip() or len(item) > 40
            for item in self.signals
        ):
            raise ValueError("signals must be a tuple of bounded strings")


def _validate_text(value: str, field_name: str, maximum: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field_name} must contain 1-{maximum} characters")


def _contains_literal(source: str, fragment: str) -> bool:
    normalize = lambda value: " ".join(
        _TOKEN_PATTERN.findall(
            "".join(
                char
                for char in unicodedata.normalize("NFKD", value.casefold())
                if not unicodedata.combining(char)
            )
        )
    )
    normalized_fragment = normalize(fragment)
    return bool(normalized_fragment) and (
        f" {normalized_fragment} " in f" {normalize(source)} "
    )


class DiscourseMentionOrigin(str, enum.Enum):
    """Backend-observed origin of one mention in the current player step."""

    TARGET_MENTION = "target_mention"
    ATTRIBUTION = "attribution"
    ACTION_ARGUMENT = "action_argument"
    SURFACE_PRONOUN = "surface_pronoun"
    RELATION_ENDPOINT = "relation_endpoint"


@dataclass(frozen=True, slots=True)
class ConversationReferenceMention:
    """Merged mention hypothesis with its deterministic extraction provenance."""

    text: str
    step_index: int
    kind_hint: SemanticObjectKind
    origins: tuple[DiscourseMentionOrigin, ...]
    start_offset: int | None = None
    end_offset: int | None = None

    def __post_init__(self) -> None:
        _validate_text(self.text, "text", 120)
        if (
            isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or self.step_index < 0
        ):
            raise ValueError("step_index must be a non-negative integer")
        if not isinstance(self.kind_hint, SemanticObjectKind):
            raise TypeError("kind_hint must be a SemanticObjectKind")
        if not isinstance(self.origins, tuple) or not self.origins:
            raise ValueError("origins must be a non-empty tuple")
        if any(not isinstance(item, DiscourseMentionOrigin) for item in self.origins):
            raise TypeError("origins must contain DiscourseMentionOrigin values")
        if len(set(self.origins)) != len(self.origins):
            raise ValueError("origins must not contain duplicates")
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("mention offsets must both be present or both be None")
        if self.start_offset is not None and (
            isinstance(self.start_offset, bool)
            or not isinstance(self.start_offset, int)
            or isinstance(self.end_offset, bool)
            or not isinstance(self.end_offset, int)
            or self.start_offset < 0
            or self.end_offset <= self.start_offset
        ):
            raise ValueError("mention offsets must be a non-empty non-negative span")


@dataclass(frozen=True, slots=True)
class EntityDiscourseEvidence:
    """All bounded antecedent evidence for one visible entity."""

    entity_id: int
    evidence: tuple[DiscourseEvidence, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.entity_id, bool)
            or not isinstance(self.entity_id, int)
            or self.entity_id < 1
        ):
            raise ValueError("entity_id must be a positive integer")
        if not isinstance(self.evidence, tuple) or not self.evidence:
            raise ValueError("evidence must be a non-empty tuple")
        if any(not isinstance(item, DiscourseEvidence) for item in self.evidence):
            raise TypeError("evidence must contain DiscourseEvidence values")


@dataclass(frozen=True, slots=True)
class DiscourseEvidenceBundle:
    """Immutable extraction result joining current mentions to scoped history evidence.

    The bundle carries no trusted entity identity for current player mentions.
    Entity IDs appear only on backend-produced antecedent evidence, after the
    caller has supplied a visibility-filtered world projection.
    """

    mentions: tuple[ConversationReferenceMention, ...]
    entity_evidence: tuple[EntityDiscourseEvidence, ...]
    selection_reason: str
    selected_turn_count: int
    selected_turn_ids: tuple[int, ...] = ()
    anchor_tokens: tuple[str, ...] = ()
    selection_ambiguous: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.mentions, tuple) or any(
            not isinstance(item, ConversationReferenceMention)
            for item in self.mentions
        ):
            raise TypeError("mentions must contain ConversationReferenceMention values")
        if not isinstance(self.entity_evidence, tuple) or any(
            not isinstance(item, EntityDiscourseEvidence)
            for item in self.entity_evidence
        ):
            raise TypeError("entity_evidence must contain EntityDiscourseEvidence values")
        entity_ids = tuple(item.entity_id for item in self.entity_evidence)
        if len(set(entity_ids)) != len(entity_ids):
            raise ValueError("entity_evidence must contain unique entity IDs")
        _validate_text(self.selection_reason, "selection_reason", 40)
        if (
            isinstance(self.selected_turn_count, bool)
            or not isinstance(self.selected_turn_count, int)
            or not 0 <= self.selected_turn_count <= 12
        ):
            raise ValueError("selected_turn_count must be between 0 and 12")
        if not isinstance(self.selected_turn_ids, tuple) or len(self.selected_turn_ids) > 12:
            raise ValueError("selected_turn_ids must be a tuple of at most 12 values")
        if any(
            isinstance(item, bool) or not isinstance(item, int) or item < 1
            for item in self.selected_turn_ids
        ):
            raise ValueError("selected_turn_ids must contain positive integers")
        if len(set(self.selected_turn_ids)) != len(self.selected_turn_ids):
            raise ValueError("selected_turn_ids must not contain duplicates")
        if not isinstance(self.anchor_tokens, tuple) or len(self.anchor_tokens) > 24:
            raise ValueError("anchor_tokens must be a tuple of at most 24 values")
        if any(
            not isinstance(item, str) or not item.strip() or len(item) > 40
            for item in self.anchor_tokens
        ):
            raise ValueError("anchor_tokens must contain bounded non-empty strings")
        if not isinstance(self.selection_ambiguous, bool):
            raise TypeError("selection_ambiguous must be a boolean")

    def evidence_for(self, entity_id: int) -> tuple[DiscourseEvidence, ...]:
        """Return only the evidence bundle for the requested visible candidate."""
        for item in self.entity_evidence:
            if item.entity_id == entity_id:
                return item.evidence
        return ()


class CandidateRankingStatus(str, enum.Enum):
    NO_CANDIDATES = "no_candidates"
    BELOW_MINIMUM_SCORE = "below_minimum_score"
    AMBIGUOUS_MARGIN = "ambiguous_margin"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class DiscourseCandidateRanking:
    """Auditable score/margin decision for one anaphoric mention."""

    mention: str
    candidates: tuple[DiscourseCandidate, ...]
    minimum_score: int
    minimum_margin: int
    status: CandidateRankingStatus

    def __post_init__(self) -> None:
        _validate_text(self.mention, "mention", 120)
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(item, DiscourseCandidate) for item in self.candidates
        ):
            raise TypeError("candidates must contain DiscourseCandidate values")
        candidate_ids = tuple(item.entity_id for item in self.candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate ranking must contain unique entity IDs")
        expected_order = tuple(sorted(
            self.candidates,
            key=lambda item: (-item.score, item.entity_id),
        ))
        if self.candidates != expected_order:
            raise ValueError("candidate ranking must be sorted by score then entity ID")
        if (
            isinstance(self.minimum_score, bool)
            or not isinstance(self.minimum_score, int)
            or not 0 <= self.minimum_score <= 1000
        ):
            raise ValueError("minimum_score must be between 0 and 1000")
        if (
            isinstance(self.minimum_margin, bool)
            or not isinstance(self.minimum_margin, int)
            or not 0 <= self.minimum_margin <= 1000
        ):
            raise ValueError("minimum_margin must be between 0 and 1000")
        if not isinstance(self.status, CandidateRankingStatus):
            raise TypeError("status must be a CandidateRankingStatus")
        expected_status = self._derive_status()
        if self.status is not expected_status:
            raise ValueError("status does not match the candidate scores and thresholds")

    def _derive_status(self) -> CandidateRankingStatus:
        if not self.candidates:
            return CandidateRankingStatus.NO_CANDIDATES
        if self.candidates[0].score < self.minimum_score:
            return CandidateRankingStatus.BELOW_MINIMUM_SCORE
        if (
            len(self.candidates) > 1
            and self.candidates[0].score - self.candidates[1].score
            < self.minimum_margin
        ):
            return CandidateRankingStatus.AMBIGUOUS_MARGIN
        return CandidateRankingStatus.RESOLVED

    @property
    def top_score(self) -> int | None:
        return self.candidates[0].score if self.candidates else None

    @property
    def runner_up_score(self) -> int | None:
        return self.candidates[1].score if len(self.candidates) > 1 else None

    @property
    def margin(self) -> int | None:
        if len(self.candidates) < 2:
            return None
        return self.candidates[0].score - self.candidates[1].score

    @property
    def selected_candidate(self) -> DiscourseCandidate | None:
        return (
            self.candidates[0]
            if self.status is CandidateRankingStatus.RESOLVED
            else None
        )

    @property
    def abstention_reason(self) -> str | None:
        return {
            CandidateRankingStatus.NO_CANDIDATES: "no_visible_antecedent_evidence",
            CandidateRankingStatus.BELOW_MINIMUM_SCORE: "discourse_candidate_below_threshold",
            CandidateRankingStatus.AMBIGUOUS_MARGIN: "discourse_candidates_ambiguous",
            CandidateRankingStatus.RESOLVED: None,
        }[self.status]
