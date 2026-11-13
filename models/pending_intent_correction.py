"""Safe, evidence-bound corrections for an uncommitted player-intent draft.

This model deliberately has no persistence or world-mutation capability. A
correction can only be applied while its durable resolution is still pending.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from enum import Enum

from models.player_intent_analysis import PlayerIntentAnalysis
from models.semantic_frames import (
    SemanticArgument,
    SemanticActionFrame,
    SemanticArgumentRole,
    SemanticMention,
    SemanticRelationClaim,
)


class PendingCorrectionSlot(str, Enum):
    TARGET_MENTION = "target_mention"
    ACTION_ARGUMENT = "action_argument"
    RELATION_SUBJECT = "relation_subject"
    RELATION_OBJECT = "relation_object"


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
            if any(
                _normalize(value) == _normalize(self.replacement.text)
                for value in step.target_mentions
                if _normalize(value) != _normalize(self.previous_value)
            ):
                raise ValueError("replacement target is already present")
            targets = tuple(
                self.replacement.text if _normalize(value) == _normalize(self.previous_value) else value
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
                action=corrected_action,
                action_frame=corrected_frame,
                target_mentions=targets,
            )

        return replace(
            analysis,
            steps=tuple(steps),
            relation_claims=tuple(claims),
        )


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


def _replace_action_reference(action: str, previous: str, replacement: str) -> str:
    updated = re.sub(re.escape(previous), lambda _match: replacement, action, flags=re.IGNORECASE)
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
