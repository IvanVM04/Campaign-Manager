"""Safe, evidence-bound corrections for an uncommitted player-intent draft.

This model deliberately has no persistence or world-mutation capability. A
correction can only be applied while its durable resolution is still pending.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from enum import Enum

from models.player_intent_analysis import (
    MAX_STEPS,
    MAX_TARGETS_PER_STEP,
    PlayerIntentAnalysis,
)
from models.semantic_frames import (
    MAX_ACTION_ARGUMENTS,
    MAX_RELATION_CLAIMS,
    SemanticActionFrame,
    SemanticArgument,
    SemanticArgumentRole,
    SemanticMention,
    SemanticRelationClaim,
)


class PendingCorrectionSlot(str, Enum):
    TARGET_MENTION = "target_mention"
    ACTION_ARGUMENT = "action_argument"
    RELATION_SUBJECT = "relation_subject"
    RELATION_OBJECT = "relation_object"


class PendingCorrectionSelectionError(ValueError):
    """Safe selector diagnostic without retaining model- or player-supplied text."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        selected_slot_id: int,
        selected_slot: PendingCorrectionSlot,
        matching_slot_id: int | None = None,
        matching_slot: PendingCorrectionSlot | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.selected_slot_id = selected_slot_id
        self.selected_slot = selected_slot
        self.matching_slot_id = matching_slot_id
        self.matching_slot = matching_slot


_CORRECTION_STEP_STRIDE = MAX_TARGETS_PER_STEP + MAX_ACTION_ARGUMENTS
_CORRECTION_RELATION_OFFSET = MAX_STEPS * _CORRECTION_STEP_STRIDE
MAX_CORRECTION_SLOTS = (
    _CORRECTION_RELATION_OFFSET + MAX_RELATION_CLAIMS * 2
)


@dataclass(frozen=True, slots=True)
class PendingCorrectionCandidate:
    """One uniquely addressable correction slot from a pending analysis."""

    slot_id: int
    step_index: int
    slot: PendingCorrectionSlot
    current_value: str
    argument_role: SemanticArgumentRole | None = None
    relation_claim_index: int | None = None

    def to_prompt_dict(self) -> dict[str, object]:
        """Return a compact ID/value pair; the parent field supplies the slot kind."""
        item: dict[str, object] = {
            "slot_id": self.slot_id,
            "current_value": self.current_value,
        }
        if self.slot is PendingCorrectionSlot.ACTION_ARGUMENT:
            if self.argument_role is None:
                raise ValueError("action-argument candidate requires an argument role")
            item["role"] = self.argument_role.value
        return item


def build_pending_correction_candidates(
    pending_analysis: PlayerIntentAnalysis,
) -> tuple[PendingCorrectionCandidate, ...]:
    """Build stable slot IDs directly from bounded pending-analysis positions.

    IDs use reserved ranges per step and relation claim, so they do not shift
    when an earlier correction changes a mention value. Duplicate target
    mentions are omitted because the current typed patch cannot safely address
    one occurrence independently. Action arguments that cannot be uniquely
    resolved by role and normalized value are omitted. Targets already
    represented by action arguments or relation endpoints are omitted too,
    because their precise typed candidates must take precedence over the
    broader target patch.
    """
    if not isinstance(pending_analysis, PlayerIntentAnalysis):
        raise TypeError("pending_analysis must be a PlayerIntentAnalysis")

    relation_endpoint_counts_by_step: dict[int, dict[str, int]] = {}
    for claim in pending_analysis.relation_claims:
        endpoint_counts = relation_endpoint_counts_by_step.setdefault(
            claim.step_index,
            {},
        )
        for mention in (claim.subject, claim.object):
            normalized_mention = _normalize(mention.text)
            endpoint_counts[normalized_mention] = (
                endpoint_counts.get(normalized_mention, 0) + 1
            )

    candidates: list[PendingCorrectionCandidate] = []
    for step_index, step in enumerate(pending_analysis.steps):
        structured_mentions = {
            _normalize(argument.mention.text)
            for argument in (
                step.action_frame.arguments
                if step.action_frame is not None
                else ()
            )
        }
        structured_mentions.update(
            _normalize(mention.text)
            for claim in pending_analysis.relation_claims
            if claim.step_index == step_index
            for mention in (claim.subject, claim.object)
        )
        normalized_targets = [_normalize(value) for value in step.target_mentions]
        for target_index, value in enumerate(step.target_mentions):
            normalized_value = normalized_targets[target_index]
            if (
                normalized_targets.count(normalized_value) != 1
                or normalized_value in structured_mentions
            ):
                continue
            candidates.append(
                PendingCorrectionCandidate(
                    slot_id=(
                        step_index * _CORRECTION_STEP_STRIDE + target_index
                    ),
                    step_index=step_index,
                    slot=PendingCorrectionSlot.TARGET_MENTION,
                    current_value=value,
                )
            )

        frame = step.action_frame
        if frame is not None:
            normalized_argument_keys = [
                (argument.role, _normalize(argument.mention.text))
                for argument in frame.arguments
            ]
            for argument_index, argument in enumerate(frame.arguments):
                key = normalized_argument_keys[argument_index]
                if (
                    normalized_argument_keys.count(key) != 1
                    or relation_endpoint_counts_by_step.get(
                        step_index,
                        {},
                    ).get(key[1], 0) == 1
                ):
                    continue
                candidates.append(
                    PendingCorrectionCandidate(
                        slot_id=(
                            step_index * _CORRECTION_STEP_STRIDE
                            + MAX_TARGETS_PER_STEP
                            + argument_index
                        ),
                        step_index=step_index,
                        slot=PendingCorrectionSlot.ACTION_ARGUMENT,
                        current_value=argument.mention.text,
                        argument_role=argument.role,
                    )
                )

    for claim_index, claim in enumerate(pending_analysis.relation_claims):
        candidates.extend(
            (
                PendingCorrectionCandidate(
                    slot_id=_CORRECTION_RELATION_OFFSET + claim_index * 2,
                    step_index=claim.step_index,
                    slot=PendingCorrectionSlot.RELATION_SUBJECT,
                    current_value=claim.subject.text,
                    relation_claim_index=claim_index,
                ),
                PendingCorrectionCandidate(
                    slot_id=_CORRECTION_RELATION_OFFSET + claim_index * 2 + 1,
                    step_index=claim.step_index,
                    slot=PendingCorrectionSlot.RELATION_OBJECT,
                    current_value=claim.object.text,
                    relation_claim_index=claim_index,
                ),
            )
        )

    return tuple(candidates)


@dataclass(frozen=True, slots=True)
class PendingIntentCorrection:
    """An explicit player correction to one slot of one pending intent step."""

    step_index: int
    slot: PendingCorrectionSlot
    previous_value: str
    replacement: SemanticMention
    source_excerpt: str
    argument_role: SemanticArgumentRole | None = None
    relation_claim_index: int | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or self.step_index < 0
        ):
            raise ValueError("step_index must be a non-negative integer")
        if not isinstance(self.slot, PendingCorrectionSlot):
            raise TypeError("slot must be a PendingCorrectionSlot")
        _validate_text(self.previous_value, "previous_value", 120)
        _validate_text(self.source_excerpt, "source_excerpt", 300)
        if not isinstance(self.replacement, SemanticMention):
            raise TypeError("replacement must be a SemanticMention")
        if self.slot is PendingCorrectionSlot.ACTION_ARGUMENT:
            if not isinstance(self.argument_role, SemanticArgumentRole):
                raise ValueError("action-argument correction requires an argument_role")
        elif self.argument_role is not None:
            raise ValueError("argument_role is only valid for action-argument corrections")
        if self.slot in {
            PendingCorrectionSlot.RELATION_SUBJECT,
            PendingCorrectionSlot.RELATION_OBJECT,
        }:
            if (
                isinstance(self.relation_claim_index, bool)
                or not isinstance(self.relation_claim_index, int)
                or self.relation_claim_index < 0
            ):
                raise ValueError("relation correction requires a non-negative claim index")
        elif self.relation_claim_index is not None:
            raise ValueError("relation_claim_index is only valid for relation corrections")

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        evidence_text: str,
    ) -> PendingIntentCorrection:
        """Decode one strict provider proposal using only the latest answer as evidence."""
        expected = {
            "step_index",
            "slot",
            "previous_value",
            "replacement",
            "source_excerpt",
            "argument_role",
            "relation_claim_index",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("pending correction has missing or unexpected fields")
        replacement = SemanticMention.from_payload(
            payload["replacement"],
            evidence_text=evidence_text,
            field_name="correction replacement",
        )
        role_value = payload["argument_role"]
        role = (
            SemanticArgumentRole(role_value)
            if role_value is not None
            else None
        )
        slot = PendingCorrectionSlot(payload["slot"])
        return cls(
            step_index=payload["step_index"],
            slot=slot,
            previous_value=payload["previous_value"],
            replacement=replacement,
            source_excerpt=payload["source_excerpt"],
            argument_role=role,
            relation_claim_index=payload["relation_claim_index"],
        )

    @classmethod
    def from_intent_payload(
        cls,
        payload: object,
        *,
        evidence_text: str,
        pending_analysis: PlayerIntentAnalysis,
    ) -> PendingIntentCorrection:
        """Decode an edit by resolving its slot ID against backend candidates.

        The model selects one catalogue ID and echoes that candidate's current
        value. Step, slot kind, role and relation index are all derived from the
        stored pending analysis rather than reconstructed by the provider.
        """
        expected = {
            "slot_id",
            "previous_value",
            "replacement",
            "source_excerpt",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("intent correction has missing or unexpected fields")
        if not isinstance(pending_analysis, PlayerIntentAnalysis):
            raise TypeError("pending_analysis must be a PlayerIntentAnalysis")

        slot_id = payload["slot_id"]
        if (
            isinstance(slot_id, bool)
            or not isinstance(slot_id, int)
            or not 0 <= slot_id < MAX_CORRECTION_SLOTS
        ):
            raise ValueError("intent correction slot_id is outside the catalogue range")

        candidates = build_pending_correction_candidates(pending_analysis)
        candidate = next(
            (item for item in candidates if item.slot_id == slot_id),
            None,
        )
        if candidate is None:
            raise ValueError("intent correction slot_id is not available in pending state")

        previous_value = payload["previous_value"]
        source_excerpt = payload["source_excerpt"]
        if not isinstance(previous_value, str) or not isinstance(source_excerpt, str):
            raise TypeError("intent correction values must be strings")
        _validate_text(previous_value, "previous_value", 120)
        _validate_text(source_excerpt, "source_excerpt", 300)

        normalized_previous = _normalize(previous_value)
        if normalized_previous != _normalize(candidate.current_value):
            matching_candidate = next(
                (
                    item
                    for item in candidates
                    if item.slot_id != candidate.slot_id
                    and item.step_index == candidate.step_index
                    and _normalize(item.current_value) == normalized_previous
                ),
                None,
            )
            if matching_candidate is not None:
                raise PendingCorrectionSelectionError(
                    "intent correction previous_value matches another pending slot",
                    reason_code="correction_previous_value_matches_other_slot",
                    selected_slot_id=candidate.slot_id,
                    selected_slot=candidate.slot,
                    matching_slot_id=matching_candidate.slot_id,
                    matching_slot=matching_candidate.slot,
                )
            raise PendingCorrectionSelectionError(
                "intent correction previous_value does not match selected pending slot",
                reason_code="correction_previous_value_mismatch",
                selected_slot_id=candidate.slot_id,
                selected_slot=candidate.slot,
            )

        replacement = SemanticMention.from_payload(
            payload["replacement"],
            evidence_text=evidence_text,
            field_name="correction replacement",
        )
        return cls(
            step_index=candidate.step_index,
            slot=candidate.slot,
            previous_value=candidate.current_value,
            replacement=replacement,
            source_excerpt=source_excerpt,
            argument_role=candidate.argument_role,
            relation_claim_index=candidate.relation_claim_index,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the bounded typed correction for durable audit history."""
        return {
            "step_index": self.step_index,
            "slot": self.slot.value,
            "previous_value": self.previous_value,
            "replacement": self.replacement.to_dict(),
            "source_excerpt": self.source_excerpt,
            "argument_role": (
                self.argument_role.value
                if self.argument_role is not None
                else None
            ),
            "relation_claim_index": self.relation_claim_index,
        }

    def matches_analysis(self, analysis: PlayerIntentAnalysis) -> bool:
        """Check that the corrected analysis reflects this exact typed edit."""
        if self.step_index >= len(analysis.steps):
            return False
        step = analysis.steps[self.step_index]
        previous = _normalize(self.previous_value)
        replacement = _normalize(self.replacement.text)
        if self.slot is PendingCorrectionSlot.TARGET_MENTION:
            values = {_normalize(value) for value in step.target_mentions}
            return replacement in values and previous not in values
        if self.slot is PendingCorrectionSlot.ACTION_ARGUMENT:
            frame = step.action_frame
            if frame is None or self.argument_role is None:
                return False
            values = {
                _normalize(argument.mention.text)
                for argument in frame.arguments
                if argument.role is self.argument_role
            }
            return replacement in values and previous not in values
        if self.relation_claim_index is None:
            return False
        if self.relation_claim_index >= len(analysis.relation_claims):
            return False
        claim = analysis.relation_claims[self.relation_claim_index]
        if claim.step_index != self.step_index:
            return False
        endpoint = (
            claim.subject
            if self.slot is PendingCorrectionSlot.RELATION_SUBJECT
            else claim.object
        )
        return (
            _normalize(endpoint.text) == replacement
            and previous != replacement
        )

    def apply(
        self,
        analysis: PlayerIntentAnalysis,
        *,
        player_evidence_text: str,
        resolution_pending: bool,
        committed: bool,
    ) -> PlayerIntentAnalysis:
        """Return a corrected copy, refusing committed or weakly grounded edits."""
        if not isinstance(analysis, PlayerIntentAnalysis):
            raise TypeError("analysis must be a PlayerIntentAnalysis")
        if not isinstance(player_evidence_text, str) or not player_evidence_text.strip():
            raise ValueError("player_evidence_text must not be empty")
        if not isinstance(resolution_pending, bool) or not isinstance(committed, bool):
            raise TypeError("pending and committed flags must be booleans")
        if not resolution_pending or committed:
            raise ValueError("only an uncommitted pending resolution may be corrected")
        if self.step_index >= len(analysis.steps):
            raise ValueError("correction references a missing intent step")
        if not _contains_literal(player_evidence_text, self.source_excerpt):
            raise ValueError("correction excerpt is not literal player evidence")
        if not _contains_literal(self.source_excerpt, self.replacement.text):
            raise ValueError("replacement mention is not grounded in correction evidence")
        if _normalize(self.previous_value) == _normalize(self.replacement.text):
            raise ValueError("correction must change the targeted value")

        steps = list(analysis.steps)
        step = steps[self.step_index]
        merged_step_excerpt = _merge_excerpt(step.source_excerpt, self.source_excerpt)
        corrected_action = _replace_action_reference(
            step.action,
            self.previous_value,
            self.replacement.text,
        )
        claims = list(analysis.relation_claims)

        if self.slot is PendingCorrectionSlot.TARGET_MENTION:
            matches = [
                index for index, value in enumerate(step.target_mentions)
                if _normalize(value) == _normalize(self.previous_value)
            ]
            if len(matches) != 1:
                raise ValueError("target correction must identify exactly one existing mention")
            targets = list(step.target_mentions)
            if any(_normalize(value) == _normalize(self.replacement.text) for value in targets):
                raise ValueError("replacement target is already present")
            targets[matches[0]] = self.replacement.text
            corrected_frame = _replace_frame_mention(
                step.action_frame,
                self.previous_value,
                self.replacement,
            )
            claims = _replace_claim_endpoints(
                claims,
                step_index=self.step_index,
                previous_value=self.previous_value,
                replacement=self.replacement,
                correction_excerpt=self.source_excerpt,
            )
            steps[self.step_index] = replace(
                step,
                source_excerpt=merged_step_excerpt,
                action=corrected_action,
                target_mentions=tuple(targets),
                action_frame=corrected_frame,
            )

        elif self.slot is PendingCorrectionSlot.ACTION_ARGUMENT:
            frame = step.action_frame
            if frame is None:
                raise ValueError("action-argument correction requires a semantic action frame")
            matches = [
                index for index, argument in enumerate(frame.arguments)
                if argument.role is self.argument_role
                and _normalize(argument.mention.text) == _normalize(self.previous_value)
            ]
            if len(matches) != 1:
                raise ValueError("argument correction must identify exactly one role/value slot")
            if any(
                _normalize(value) == _normalize(self.replacement.text)
                for value in step.target_mentions
                if _normalize(value) != _normalize(self.previous_value)
            ):
                raise ValueError("replacement target is already present")
            argument_role = self.argument_role
            if not isinstance(argument_role, SemanticArgumentRole):
                raise ValueError("action-argument correction requires an argument role")
            arguments = list(frame.arguments)
            arguments[matches[0]] = SemanticArgument(
                role=argument_role,
                mention=self.replacement,
            )
            corrected_frame = replace(frame, arguments=tuple(arguments))
            targets = tuple(
                self.replacement.text if _normalize(value) == _normalize(self.previous_value) else value
                for value in step.target_mentions
            )
            claims = _replace_claim_endpoints(
                claims,
                step_index=self.step_index,
                previous_value=self.previous_value,
                replacement=self.replacement,
                correction_excerpt=self.source_excerpt,
            )
            steps[self.step_index] = replace(
                step,
                source_excerpt=merged_step_excerpt,
                action=corrected_action,
                action_frame=corrected_frame,
                target_mentions=targets,
            )

        else:
            if self.relation_claim_index is None or self.relation_claim_index >= len(claims):
                raise ValueError("relation correction references a missing claim")
            claim = claims[self.relation_claim_index]
            if claim.step_index != self.step_index:
                raise ValueError("relation correction must target a claim in the same step")
            field_name = (
                "subject"
                if self.slot is PendingCorrectionSlot.RELATION_SUBJECT
                else "object"
            )
            current = getattr(claim, field_name)
            if _normalize(current.text) != _normalize(self.previous_value):
                raise ValueError("relation correction does not match the pending endpoint")

            normalized_previous = _normalize(self.previous_value)
            relation_occurrences = sum(
                1
                for related_claim in claims
                if related_claim.step_index == self.step_index
                for mention in (related_claim.subject, related_claim.object)
                if _normalize(mention.text) == normalized_previous
            )
            target_occurrences = sum(
                1
                for value in step.target_mentions
                if _normalize(value) == normalized_previous
            )
            frame_occurrences = (
                sum(
                    1
                    for argument in step.action_frame.arguments
                    if _normalize(argument.mention.text) == normalized_previous
                )
                if step.action_frame is not None
                else 0
            )
            action_occurrences = _literal_occurrences(
                step.action,
                self.previous_value,
            )
            if any(
                _normalize(value) == _normalize(self.replacement.text)
                for value in step.target_mentions
                if _normalize(value) != normalized_previous
            ):
                raise ValueError("replacement target is already present")

            corrected_subject = (
                self.replacement if field_name == "subject" else claim.subject
            )
            corrected_object = (
                self.replacement if field_name == "object" else claim.object
            )
            claims[self.relation_claim_index] = replace(
                claim,
                subject=corrected_subject,
                object=corrected_object,
                source_excerpt=_merge_excerpt(
                    claim.source_excerpt,
                    self.source_excerpt,
                ),
            )

            synchronize_step_projection = (
                relation_occurrences == 1
                and target_occurrences <= 1
                and frame_occurrences <= 1
                and action_occurrences <= 1
            )
            if synchronize_step_projection:
                targets = tuple(
                    self.replacement.text
                    if _normalize(value) == normalized_previous
                    else value
                    for value in step.target_mentions
                )
                corrected_frame = _replace_frame_mention(
                    step.action_frame,
                    self.previous_value,
                    self.replacement,
                )
                steps[self.step_index] = replace(
                    step,
                    source_excerpt=merged_step_excerpt,
                    action=_replace_action_reference(
                        step.action,
                        self.previous_value,
                        self.replacement.text,
                    ),
                    action_frame=corrected_frame,
                    target_mentions=targets,
                )
            else:
                # A relation selector addresses exactly one claim. If the same
                # mention appears elsewhere in the step, changing its broad
                # projection would silently edit those other references too.
                steps[self.step_index] = replace(
                    step,
                    source_excerpt=merged_step_excerpt,
                )

        return replace(
            analysis,
            steps=tuple(steps),
            relation_claims=tuple(claims),
        )


def apply_pending_intent_corrections(
    pending_analysis: PlayerIntentAnalysis,
    corrections: tuple[PendingIntentCorrection, ...],
    *,
    player_evidence_text: str,
    require_catalogue_match: bool = True,
) -> PlayerIntentAnalysis:
    """Validate and atomically apply a batch against one immutable catalogue.

    Every selector is resolved against the exact pending analysis shown to the
    provider. The resulting patches are then applied to a private staged copy.
    No caller-visible state is changed unless the complete batch succeeds.
    """
    if not isinstance(pending_analysis, PlayerIntentAnalysis):
        raise TypeError("pending_analysis must be a PlayerIntentAnalysis")
    if not isinstance(corrections, tuple):
        raise TypeError("corrections must be a tuple")
    if len(corrections) > 4:
        raise ValueError("pending correction batch exceeds the four-edit limit")
    if not isinstance(player_evidence_text, str) or not player_evidence_text.strip():
        raise ValueError("pending correction evidence must not be empty")
    if len(player_evidence_text) > 5000:
        raise ValueError("pending correction evidence exceeds the 5000-character limit")
    if not isinstance(require_catalogue_match, bool):
        raise TypeError("require_catalogue_match must be a boolean")
    if not corrections:
        return pending_analysis

    # Freeze the selector universe before validating any member of the batch.
    candidates = (
        build_pending_correction_candidates(pending_analysis)
        if require_catalogue_match
        else ()
    )
    selected_slot_ids: set[int] = set()
    edited_mentions: set[tuple[int, str]] = set()
    replacements_by_step: dict[int, set[str]] = {}
    previous_mentions_by_step: dict[int, set[str]] = {}
    current_mentions_by_step: dict[int, set[str]] = {}

    for correction in corrections:
        if not isinstance(correction, PendingIntentCorrection):
            raise TypeError("correction batch contains a non-correction value")
        step_index = correction.step_index
        if step_index >= len(pending_analysis.steps):
            raise ValueError("correction batch references a missing intent step")

        previous = _normalize(correction.previous_value)
        replacement = _normalize(correction.replacement.text)
        edit_key = (step_index, previous)
        if edit_key in edited_mentions:
            raise ValueError("correction batch contains overlapping mention edits")
        edited_mentions.add(edit_key)
        previous_mentions_by_step.setdefault(step_index, set()).add(previous)

        if require_catalogue_match:
            matching = [
                candidate
                for candidate in candidates
                if candidate.step_index == step_index
                and candidate.slot is correction.slot
                and _normalize(candidate.current_value) == previous
                and candidate.argument_role is correction.argument_role
                and candidate.relation_claim_index == correction.relation_claim_index
            ]
            if len(matching) != 1:
                raise ValueError(
                    "correction does not address a candidate from the initial pending state"
                )
            slot_id = matching[0].slot_id
            if slot_id in selected_slot_ids:
                raise ValueError("correction batch selects a duplicate catalogue slot")
            selected_slot_ids.add(slot_id)

        step = pending_analysis.steps[step_index]
        current_mentions = current_mentions_by_step.setdefault(step_index, set())
        current_mentions.update(_normalize(value) for value in step.target_mentions)
        if step.action_frame is not None:
            current_mentions.update(
                _normalize(argument.mention.text)
                for argument in step.action_frame.arguments
            )
        current_mentions.update(
            _normalize(mention.text)
            for claim in pending_analysis.relation_claims
            if claim.step_index == step_index
            for mention in (claim.subject, claim.object)
        )
        if replacement in current_mentions and replacement != previous:
            raise ValueError("correction replacement already exists in the pending step")
        replacement_set = replacements_by_step.setdefault(step_index, set())
        if replacement in replacement_set:
            raise ValueError("correction batch contains duplicate replacement mentions")
        replacement_set.add(replacement)

    for correction in corrections:
        step_index = correction.step_index
        replacement = _normalize(correction.replacement.text)
        previous = _normalize(correction.previous_value)
        if (
            replacement != previous
            and replacement in previous_mentions_by_step.get(step_index, set())
        ):
            raise ValueError(
                "correction replacement overlaps another selected pending mention"
            )

    staged_analysis = pending_analysis
    for correction in corrections:
        staged_analysis = correction.apply(
            staged_analysis,
            player_evidence_text=player_evidence_text,
            resolution_pending=True,
            committed=False,
        )
    return staged_analysis


def _validate_text(value: str, field_name: str, maximum: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field_name} must contain 1-{maximum} characters")


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def _contains_literal(source: str, fragment: str) -> bool:
    normalized_fragment = _normalize(fragment)
    return bool(normalized_fragment) and (
        f" {normalized_fragment} " in f" {_normalize(source)} "
    )


def _merge_excerpt(original: str, correction: str) -> str:
    merged = f"{original.rstrip()} {correction.strip()}".strip()
    if len(merged) > 300:
        raise ValueError(
            "corrected evidence exceeds the 300-character semantic-step budget"
        )
    return merged


def _literal_occurrences(source: str, fragment: str) -> int:
    pattern = rf"(?<!\w){re.escape(fragment)}(?!\w)"
    return len(re.findall(pattern, source, flags=re.IGNORECASE))


def _replace_action_reference(action: str, previous: str, replacement: str) -> str:
    pattern = rf"(?<!\w){re.escape(previous)}(?!\w)"
    updated = re.sub(
        pattern,
        lambda _match: replacement,
        action,
        flags=re.IGNORECASE,
    )
    if len(updated) > 500:
        raise ValueError("corrected action exceeds the 500-character limit")
    return updated


def _replace_frame_mention(
    frame: SemanticActionFrame | None,
    previous: str,
    replacement: SemanticMention,
) -> SemanticActionFrame | None:
    if frame is None:
        return None
    arguments = tuple(
        replace(argument, mention=replacement)
        if _normalize(argument.mention.text) == _normalize(previous)
        else argument
        for argument in frame.arguments
    )
    return replace(frame, arguments=arguments)


def _replace_claim_endpoints(
    claims: list[SemanticRelationClaim],
    *,
    step_index: int,
    previous_value: str,
    replacement: SemanticMention,
    correction_excerpt: str,
) -> list[SemanticRelationClaim]:
    updated: list[SemanticRelationClaim] = list(claims)
    for index, claim in enumerate(updated):
        if claim.step_index != step_index:
            continue
        subject = (
            replacement
            if _normalize(claim.subject.text) == _normalize(previous_value)
            else claim.subject
        )
        object_mention = (
            replacement
            if _normalize(claim.object.text) == _normalize(previous_value)
            else claim.object
        )
        if subject != claim.subject or object_mention != claim.object:
            updated[index] = replace(
                claim,
                subject=subject,
                object=object_mention,
                source_excerpt=_merge_excerpt(
                    claim.source_excerpt,
                    correction_excerpt,
                ),
            )
    return updated
